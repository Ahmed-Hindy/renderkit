#include "main_window.hpp"
#include "collapsible_group.hpp"
#include "core/constants.hpp"
#include "core/exceptions.hpp"
#include "core/logging.hpp"
#include "core/path_utils.hpp"
#include "core/sequence_names.hpp"
#include "custom_widgets.hpp"
#include "io/file_utils.hpp"
#include "io/image_reader.hpp"
#include "preview_widget.hpp"
#include <OpenImageIO/color.h>
#include <QApplication>
#include <QCheckBox>
#include <QCloseEvent>
#include <QComboBox>
#include <QDesktopServices>
#include <QDir>
#include <QDoubleSpinBox>
#include <QDragEnterEvent>
#include <QDragLeaveEvent>
#include <QDropEvent>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QMimeData>
#include <QPixmap>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSettings>
#include <QShortcut>
#include <QSignalBlocker>
#include <QSlider>
#include <QSpinBox>
#include <QSplitter>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <map>
#include <mutex>
#include <set>
#include <tuple>

namespace rk {
struct UiLogState {
    std::mutex mutex;
    QPlainTextEdit *target = nullptr;
};
namespace {
QSpinBox *spin(const char *name, int min, int max, int value, QWidget *parent) {
    auto *widget = new NoWheelSpinBox(parent);
    widget->setObjectName(name);
    widget->setRange(min, max);
    widget->setValue(value);
    return widget;
}
QCheckBox *check(const char *name, const QString &text, bool value, QWidget *parent) {
    auto *widget = new QCheckBox(text, parent);
    widget->setObjectName(name);
    widget->setChecked(value);
    return widget;
}
QWidget *row(std::initializer_list<QWidget *> widgets, QWidget *parent) {
    auto *container = new QWidget(parent);
    auto *layout = new QHBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    for (auto *widget : widgets)
        layout->addWidget(widget);
    return container;
}
void set_validation_state(QComboBox *input, const QString &state) {
    for (QWidget *widget :
         {static_cast<QWidget *>(input), static_cast<QWidget *>(input->lineEdit())}) {
        if (!widget)
            continue;
        widget->setProperty("validationState", state);
        widget->style()->unpolish(widget);
        widget->style()->polish(widget);
        widget->update();
    }
}
bool supported_image(const std::filesystem::path &path) {
    auto extension = path_to_utf8(path.extension());
    if (!extension.empty() && extension.front() == '.')
        extension.erase(extension.begin());
    std::transform(
        extension.begin(), extension.end(), extension.begin(),
        [](unsigned char character) { return static_cast<char>(std::tolower(character)); });
    return std::find(constants::kOiioSupportedExtensions.begin(),
                     constants::kOiioSupportedExtensions.end(),
                     extension) != constants::kOiioSupportedExtensions.end();
}
} // namespace
MainWindow::MainWindow(const QString &initial_path, QWidget *parent) : QMainWindow(parent) {
    setWindowTitle("RenderKit v2.0.0");
    resize(1400, 950);
    setMinimumSize(500, 450);
    setAcceptDrops(true);
    setProperty("theme", "dark");
    auto *splitter = new QSplitter(this);
    splitter_ = splitter;
    setCentralWidget(splitter);
    auto *scroll = new QScrollArea(splitter);
    scroll->setWidgetResizable(true);
    auto *controls = new QWidget(scroll);
    auto *sections = new QVBoxLayout(controls);
    auto *input_group = new CollapsibleGroup("Input Sequence", true, controls);
    sections->addWidget(input_group);
    auto *input_form = new QFormLayout;
    input_group->content_layout()->addLayout(input_form);
    input_ = new NoWheelComboBox(controls);
    input_->setObjectName("input_pattern_combo");
    input_->setEditable(true);
    auto *browse_input = new QPushButton("Browse…", controls);
    browse_input->setObjectName("browse_input_btn");
    input_form->addRow("Sequence", row({input_, browse_input}, controls));
    sequence_info_ = new QLabel("Choose an image sequence", controls);
    sequence_info_->setObjectName("sequence_info_label");
    input_form->addRow(sequence_info_);
    layer_ = new NoWheelComboBox(controls);
    layer_->setObjectName("layer_combo");
    layer_->addItem("RGBA");
    sheet_ = check("cs_enable_check", "Contact Sheet", false, controls);
    input_form->addRow("Layer", row({layer_, sheet_}, controls));
    color_ = new NoWheelComboBox(controls);
    color_->setObjectName("color_space_combo");
    color_->addItem("Linear to sRGB", static_cast<int>(ColorSpacePreset::LinearToSrgb));
    color_->addItem("Linear to Rec.709", static_cast<int>(ColorSpacePreset::LinearToRec709));
    color_->addItem("sRGB to linear", static_cast<int>(ColorSpacePreset::SrgbToLinear));
    color_->addItem("No conversion", static_cast<int>(ColorSpacePreset::NoConversion));
    if (std::filesystem::is_regular_file(ocio_path())) {
        OIIO::ColorConfig config(path_to_utf8(ocio_path()));
        if (!config.has_error()) {
            for (const auto &role : config.getRoles()) {
                const char *space = config.getColorSpaceNameByRole(role);
                if (!space || !*space)
                    continue;
                color_->addItem(QString::fromStdString(role) + " (" + QString::fromUtf8(space) +
                                    ")",
                                static_cast<int>(ColorSpacePreset::OcioConversion));
                color_->setItemData(color_->count() - 1, QString::fromStdString(role),
                                    Qt::UserRole + 1);
            }
        }
    }
    input_form->addRow("Color", color_);
    auto *output_group = new CollapsibleGroup("Output Settings", false, controls);
    sections->addWidget(output_group);
    auto *output_form = new QFormLayout;
    output_group->content_layout()->addLayout(output_form);
    output_ = new QLineEdit(controls);
    output_->setObjectName("output_path_edit");
    auto *browse_output = new QPushButton("Browse…", controls);
    browse_output->setObjectName("browse_output_btn");
    output_form->addRow("Output", row({output_, browse_output}, controls));
    start_ = spin("start_frame_spin", -10000000, 10000000, 1001, controls);
    end_ = spin("end_frame_spin", -10000000, 10000000, 1100, controls);
    keep_range_ = check("keep_source_frame_range_check", "Use source range", true, controls);
    output_form->addRow("Frames", row({start_, end_, keep_range_}, controls));
    fps_ = new NoWheelDoubleSpinBox(controls);
    fps_->setObjectName("fps_spin");
    fps_->setRange(0.01, 120);
    fps_->setDecimals(3);
    fps_->setValue(24);
    keep_fps_ = check("keep_source_fps_check", "Use source FPS", true, controls);
    output_form->addRow("FPS", row({fps_, keep_fps_}, controls));
    width_ = spin("width_spin", 1, 7680, 1920, controls);
    height_ = spin("height_spin", 1, 4320, 1080, controls);
    aspect_link_ = new QPushButton("🔗", controls);
    aspect_link_->setObjectName("AspectLinkButton");
    aspect_link_->setCheckable(true);
    aspect_link_->setChecked(true);
    aspect_link_->setToolTip("Link aspect ratio");
    keep_resolution_ = check("keep_resolution_check", "Use source size", true, controls);
    output_form->addRow("Resolution",
                        row({width_, aspect_link_, height_, keep_resolution_}, controls));
    play_output_ = new QPushButton("Play Result (Flipbook)", controls);
    play_output_->setObjectName("IconButton");
    open_output_ = new QPushButton("Open Output Folder", controls);
    open_output_->setObjectName("IconButton");
    output_form->addRow(row({play_output_, open_output_}, controls));
    connect(output_, &QLineEdit::textChanged, this, &MainWindow::update_output_actions);
    update_output_actions();
    auto *burn_group = new CollapsibleGroup("Burn-in Overlays", false, controls);
    sections->addWidget(burn_group);
    auto *burn_form = new QFormLayout;
    burn_group->content_layout()->addLayout(burn_form);
    burnin_ = check("burnin_enable_check", "Enable burn-ins", false, controls);
    burn_form->addRow(burnin_);
    burnin_frame_ = check("burnin_frame_check", "Frame", true, controls);
    burnin_layer_ = check("burnin_layer_check", "Layer", false, controls);
    burnin_fps_ = check("burnin_fps_check", "FPS", false, controls);
    burn_form->addRow("Elements", row({burnin_frame_, burnin_layer_, burnin_fps_}, controls));
    font_size_ = spin("burnin_font_size_spin", 6, 72, 20, controls);
    opacity_ = spin("burnin_opacity_spin", 0, 100, 30, controls);
    opacity_->setSuffix("%");
    burn_form->addRow("Font size", font_size_);
    burn_form->addRow("Background", opacity_);
    sheet_group_ = new CollapsibleGroup("Contact Sheet", false, controls);
    sections->addWidget(sheet_group_);
    auto *sheet_form = new QFormLayout;
    sheet_group_->content_layout()->addLayout(sheet_form);
    columns_ = spin("cs_columns_spin", 1, 20, 4, controls);
    padding_ = spin("cs_padding_spin", 0, 100, 4, controls);
    sheet_form->addRow("Columns", columns_);
    sheet_form->addRow("Padding", padding_);
    auto *advanced = new CollapsibleGroup("Advanced Options", false, controls);
    sections->addWidget(advanced);
    auto *advanced_form = new QFormLayout;
    advanced->content_layout()->addLayout(advanced_form);
    codec_ = new NoWheelComboBox(controls);
    codec_->setObjectName("codec_combo");
    codec_->addItem("H.264 (AVC) - Default", "libx264");
    codec_->addItem("H.265 (HEVC)", "libx265");
    codec_->addItem("AV1 - Maximum Compression", "libaom-av1");
    advanced_form->addRow("Codec", codec_);
    quality_ = new NoWheelSlider(Qt::Horizontal, controls);
    quality_->setObjectName("quality_slider");
    quality_->setRange(0, 10);
    quality_->setValue(10);
    auto *quality_label = new QLabel("10 (Max)", controls);
    quality_label->setObjectName("quality_value_label");
    connect(quality_, &QSlider::valueChanged, quality_label, [quality_label](int value) {
        const auto suffix = value == 0    ? " (Min)"
                            : value == 5  ? " (Med)"
                            : value == 8  ? " (VFX)"
                            : value == 10 ? " (Max)"
                                          : "";
        quality_label->setText(QString::number(value) + suffix);
    });
    advanced_form->addRow("Quality", row({quality_, quality_label}, controls));
    workers_ = spin("prefetch_workers_spin", 1, 16, 2, controls);
    preview_scale_ = spin("preview_scale_spin", 5, 100, 75, controls);
    preview_scale_->setSuffix("%");
    overwrite_ = check("overwrite_check", "Overwrite existing output", true, controls);
    advanced_form->addRow("Prefetch workers", workers_);
    advanced_form->addRow("Preview scale", preview_scale_);
    advanced_form->addRow(overwrite_);
    sections->addStretch();
    scroll->setWidget(controls);
    auto *right = new QWidget(splitter);
    auto *right_layout = new QVBoxLayout(right);
    preview_ = new PreviewWidget(right);
    preview_->setObjectName("preview_panel");
    preview_->set_output_path(output_->text());
    connect(output_, &QLineEdit::textChanged, preview_, &PreviewWidget::set_output_path);
    preview_splitter_ = new QSplitter(Qt::Vertical, right);
    preview_splitter_->setObjectName("preview_log_splitter");
    preview_splitter_->addWidget(preview_);
    auto *log_panel = new QWidget(preview_splitter_);
    auto *log_layout = new QVBoxLayout(log_panel);
    log_layout->setContentsMargins(0, 0, 0, 0);
    log_layout->addWidget(new QLabel("Activity log", log_panel));
    log_ = new QPlainTextEdit(log_panel);
    log_->setObjectName("LogBox");
    log_->setReadOnly(true);
    log_->setMaximumBlockCount(1000);
    log_layout->addWidget(log_);
    log_state_ = std::make_shared<UiLogState>();
    log_state_->target = log_;
    try {
        setup_logging([state = log_state_](const std::string &line) {
            std::lock_guard lock(state->mutex);
            if (auto *target = state->target) {
                const auto text = QString::fromUtf8(line.data(), static_cast<int>(line.size()));
                QMetaObject::invokeMethod(
                    target, [target, text] { target->appendPlainText(text); },
                    Qt::QueuedConnection);
            }
        });
    } catch (const std::exception &) {
        log_->appendPlainText("Could not initialize file logging");
    }
    auto *clear_log = new QPushButton("Clear Logs", log_panel);
    clear_log->setObjectName("clear_logs_btn");
    connect(clear_log, &QPushButton::clicked, log_, &QPlainTextEdit::clear);
    log_layout->addWidget(clear_log, 0, Qt::AlignRight);
    preview_splitter_->addWidget(log_panel);
    preview_splitter_->setStretchFactor(0, 4);
    preview_splitter_->setStretchFactor(1, 1);
    right_layout->addWidget(preview_splitter_, 1);
    timeline_ = new JumpToClickSlider(Qt::Horizontal, right);
    timeline_->setObjectName("timeline_slider");
    timeline_->setEnabled(false);
    timeline_start_ = new QLabel("--", right);
    timeline_end_ = new QLabel("--", right);
    timeline_current_ = new QLabel("Frame: -", right);
    timeline_start_->setObjectName("TimelineLabel");
    timeline_end_->setObjectName("TimelineLabel");
    timeline_current_->setObjectName("TimelineCurrentLabel");
    timeline_current_->setAlignment(Qt::AlignCenter);
    right_layout->addWidget(row({timeline_start_, timeline_, timeline_end_}, right));
    right_layout->addWidget(timeline_current_);
    progress_label_ = new QLabel("Ready", right);
    progress_ = new QProgressBar(right);
    progress_->setValue(0);
    right_layout->addWidget(progress_label_);
    right_layout->addWidget(progress_);
    convert_ = new QPushButton("Convert", right);
    convert_->setObjectName("convert_btn");
    right_layout->addWidget(convert_);
    splitter->addWidget(scroll);
    splitter->addWidget(right);
    splitter->setSizes({650, 750});
    drop_overlay_ = new QLabel("Drop file or folder anywhere", this);
    drop_overlay_->setObjectName("DropOverlay");
    drop_overlay_->setAlignment(Qt::AlignCenter);
    drop_overlay_->setAttribute(Qt::WA_TransparentForMouseEvents);
    drop_overlay_->hide();
    preview_timer_ = new QTimer(this);
    preview_timer_->setSingleShot(true);
    preview_timer_->setInterval(40);
    connect(preview_timer_, &QTimer::timeout, this, [this] { request_preview(scrubbing_); });
    connect(timeline_, &QSlider::valueChanged, this, [this](int index) {
        if (sequence_ && index >= 0 && index < static_cast<int>(sequence_->frame_numbers.size()))
            timeline_current_->setText(QString("Frame: %1").arg(sequence_->frame_numbers[index]));
        preview_timer_->start();
    });
    connect(timeline_, &QSlider::sliderPressed, this, [this] { scrubbing_ = true; });
    connect(timeline_, &QSlider::sliderReleased, this, [this] {
        scrubbing_ = false;
        preview_timer_->stop();
        request_preview();
    });
    connect(browse_input, &QPushButton::clicked, this, [this] {
        QSettings settings("RenderKit", "RenderKit");
        const auto file = QFileDialog::getOpenFileName(this, "Open image sequence",
                                                       settings.value("last_input_dir").toString());
        if (!file.isEmpty())
            load_sequence(file);
    });
    connect(browse_output, &QPushButton::clicked, this, [this] {
        QSettings settings("RenderKit", "RenderKit");
        const auto file = QFileDialog::getSaveFileName(
            this, "Save video",
            output_->text().isEmpty() ? settings.value("last_output_dir").toString()
                                      : output_->text(),
            "Video (*.mp4 *.mov)");
        if (!file.isEmpty()) {
            output_->setText(file);
            settings.setValue("last_output_dir", QFileInfo(file).absolutePath());
        }
    });
    connect(open_output_, &QPushButton::clicked, this, [this] { open_output(true); });
    connect(play_output_, &QPushButton::clicked, this, [this] { open_output(false); });
    connect(input_->lineEdit(), &QLineEdit::editingFinished, this, [this] {
        if (!input_->currentText().isEmpty())
            load_sequence(input_->currentText());
    });
    connect(input_->lineEdit(), &QLineEdit::textEdited, this, [this] {
        ++sequence_generation_;
        ++preview_generation_;
        timeline_start_->setText("--");
        timeline_end_->setText("--");
        timeline_current_->setText("Frame: -");
        if (current_info_) {
            disconnect(current_info_, &FileInfoWorker::info_ready, this, nullptr);
            disconnect(current_info_, &FileInfoWorker::info_failed, this, nullptr);
        }
        if (current_preview_) {
            disconnect(current_preview_, &PreviewWorker::preview_ready, this, nullptr);
            disconnect(current_preview_, &PreviewWorker::preview_failed, this, nullptr);
        }
        preview_pending_ = false;
        sequence_.reset();
        source_fps_.reset();
        source_color_.reset();
        timeline_->setEnabled(false);
        preview_->set_message("Preview");
        sequence_info_->setText("No sequence detected");
        set_validation_state(input_, "");
    });
    connect(input_, &QComboBox::activated, this, [this](int index) {
        if (input_->itemData(index).toString() == "clear_recent") {
            const auto current =
                sequence_ ? QString::fromStdString(path_to_utf8(sequence_->base_path /
                                                                path_from_utf8(sequence_->pattern)))
                          : QString{};
            QSettings("RenderKit", "RenderKit").remove("recent_patterns");
            input_->clear();
            input_->setEditText(current);
        } else
            load_sequence(input_->itemText(index));
    });
    connect(sheet_, &QCheckBox::toggled, this, [this](bool enabled) {
        layer_->setEnabled(!enabled);
        if (enabled)
            sheet_group_->set_expanded(true);
        request_preview();
    });
    connect(layer_, &QComboBox::currentIndexChanged, this, [this] { request_preview(); });
    connect(color_, &QComboBox::currentIndexChanged, this, [this] { request_preview(); });
    connect(keep_fps_, &QCheckBox::toggled, fps_, &QWidget::setDisabled);
    connect(keep_range_, &QCheckBox::toggled, start_, &QWidget::setDisabled);
    connect(keep_range_, &QCheckBox::toggled, end_, &QWidget::setDisabled);
    connect(keep_resolution_, &QCheckBox::toggled, width_, &QWidget::setDisabled);
    connect(keep_resolution_, &QCheckBox::toggled, height_, &QWidget::setDisabled);
    connect(keep_resolution_, &QCheckBox::toggled, aspect_link_, &QWidget::setDisabled);
    connect(width_, &QSpinBox::valueChanged, this, [this](int value) {
        if (aspect_link_->isChecked() && aspect_ratio_ > 0) {
            QSignalBlocker blocker(height_);
            height_->setValue(static_cast<int>(std::round(value / aspect_ratio_)));
        }
    });
    connect(height_, &QSpinBox::valueChanged, this, [this](int value) {
        if (aspect_link_->isChecked() && aspect_ratio_ > 0) {
            QSignalBlocker blocker(width_);
            width_->setValue(static_cast<int>(std::round(value * aspect_ratio_)));
        }
    });
    connect(aspect_link_, &QPushButton::toggled, this, [this](bool linked) {
        if (linked && height_->value())
            aspect_ratio_ = width_->value() / double(height_->value());
    });
    for (auto *widget : {burnin_, burnin_frame_, burnin_layer_, burnin_fps_})
        connect(widget, &QCheckBox::toggled, this, [this] { preview_timer_->start(); });
    for (auto *widget : {font_size_, opacity_, columns_, padding_, preview_scale_})
        connect(widget, &QSpinBox::valueChanged, this, [this] { preview_timer_->start(); });
    connect(fps_, &QDoubleSpinBox::valueChanged, this, [this] { preview_timer_->start(); });
    connect(convert_, &QPushButton::clicked, this, &MainWindow::start_conversion);
    auto *convert_shortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_Return), this);
    connect(convert_shortcut, &QShortcut::activated, this, &MainWindow::start_conversion);
    auto *cancel_shortcut = new QShortcut(QKeySequence(Qt::Key_Escape), this);
    connect(cancel_shortcut, &QShortcut::activated, this, [this] {
        if (conversion_ &&
            QMessageBox::question(this, "Cancel conversion?", "Cancel the running conversion?") ==
                QMessageBox::Yes)
            conversion_->cancel();
    });
    auto *help_shortcut = new QShortcut(QKeySequence(Qt::Key_F1), this);
    connect(help_shortcut, &QShortcut::activated, this, [this] {
        QMessageBox::about(this, "About RenderKit",
                           "RenderKit v2.0.0\nImage sequence to video converter");
    });
    restore_settings();
    fps_->setDisabled(keep_fps_->isChecked());
    start_->setDisabled(keep_range_->isChecked());
    end_->setDisabled(keep_range_->isChecked());
    width_->setDisabled(keep_resolution_->isChecked());
    height_->setDisabled(keep_resolution_->isChecked());
    aspect_link_->setDisabled(keep_resolution_->isChecked());
    if (!initial_path.isEmpty())
        load_sequence(initial_path);
}
MainWindow::~MainWindow() {
    {
        std::lock_guard lock(log_state_->mutex);
        log_state_->target = nullptr;
    }
    if (conversion_) {
        conversion_->cancel();
        conversion_->wait();
    }
    for (auto worker : previews_)
        if (worker)
            worker->wait();
    for (auto worker : info_workers_)
        if (worker)
            worker->wait();
}
std::filesystem::path MainWindow::ocio_path() const {
    auto bundled = QDir(QCoreApplication::applicationDirPath()).filePath("data/ocio/config.ocio");
    if (QFileInfo::exists(bundled))
        return path_from_utf8(bundled.toStdString());
    return std::filesystem::path("resources/ocio/config.ocio");
}
ContactSheetConfig MainWindow::contact_sheet_config() const {
    ContactSheetConfig config;
    config.columns = columns_->value();
    config.padding = padding_->value();
    config.validate();
    return config;
}
BurnInConfig MainWindow::burnin_config() const {
    BurnInConfig config;
    config.background_opacity = opacity_->value();
    for (const auto &[enabled, text, alignment] :
         {std::tuple{burnin_frame_, "Frame: {frame}", "left"},
          std::tuple{burnin_layer_, "Layer: {layer}", "center"},
          std::tuple{burnin_fps_, "FPS: {fps:.2f}", "right"}}) {
        if (enabled->isChecked()) {
            BurnInElement element;
            element.text_template = text;
            element.alignment = alignment;
            element.x = 0;
            element.y = 0;
            element.font_size = font_size_->value();
            config.elements.push_back(element);
        }
    }
    return config;
}
void MainWindow::load_sequence(const QString &input) {
    const auto generation = ++sequence_generation_;
    ++preview_generation_;
    timeline_start_->setText("--");
    timeline_end_->setText("--");
    timeline_current_->setText("Frame: -");
    if (current_info_) {
        disconnect(current_info_, &FileInfoWorker::info_ready, this, nullptr);
        disconnect(current_info_, &FileInfoWorker::info_failed, this, nullptr);
    }
    if (current_preview_) {
        disconnect(current_preview_, &PreviewWorker::preview_ready, this, nullptr);
        disconnect(current_preview_, &PreviewWorker::preview_failed, this, nullptr);
    }
    preview_pending_ = false;
    sequence_.reset();
    timeline_->setEnabled(false);
    set_validation_state(input_, "");
    sequence_info_->setText("Reading sequence…");
    auto *worker = new FileInfoWorker(input, this);
    current_info_ = worker;
    info_workers_.append(worker);
    connect(
        worker, &FileInfoWorker::info_ready, this,
        [this, generation](const QString &pattern_text, const FrameSequence &sequence,
                           const FileInfo &info) {
            if (generation != sequence_generation_)
                return;
            sequence_ = sequence;
            log_->appendPlainText("Loaded sequence: " + pattern_text);
            source_fps_ = info.fps;
            source_color_ = info.color_space;
            {
                QSignalBlocker blocker(color_);
                const bool use_source =
                    color_->currentIndex() == 0 || color_->currentData(Qt::UserRole + 2).toBool();
                for (int i = color_->count() - 1; i >= 0; --i)
                    if (color_->itemData(i, Qt::UserRole + 2).toBool())
                        color_->removeItem(i);
                if (use_source) {
                    color_->setCurrentIndex(0);
                    if (source_color_) {
                        const auto space = QString::fromStdString(*source_color_);
                        color_->addItem("Source: " + space,
                                        static_cast<int>(ColorSpacePreset::OcioConversion));
                        const int index = color_->count() - 1;
                        color_->setItemData(index, space, Qt::UserRole + 1);
                        color_->setItemData(index, true, Qt::UserRole + 2);
                        color_->setCurrentIndex(index);
                    }
                }
            }
            set_validation_state(input_, "valid");
            QSettings settings("RenderKit", "RenderKit");
            auto recent = settings.value("recent_patterns").toStringList();
            recent.removeAll(pattern_text);
            recent.prepend(pattern_text);
            while (recent.size() > 10)
                recent.removeLast();
            settings.setValue("recent_patterns", recent);
            settings.setValue("last_input_dir",
                              QString::fromStdString(path_to_utf8(sequence_->base_path)));
            input_->blockSignals(true);
            input_->clear();
            input_->addItems(recent);
            input_->addItem("Clear recent patterns", "clear_recent");
            input_->setEditText(pattern_text);
            input_->blockSignals(false);
            sequence_info_->setText(QString("%1 frames · %2–%3 · %4 × %5")
                                        .arg(sequence_->frame_numbers.size())
                                        .arg(sequence_->frame_numbers.front())
                                        .arg(sequence_->frame_numbers.back())
                                        .arg(info.width)
                                        .arg(info.height));
            start_->setValue(sequence_->frame_numbers.front());
            end_->setValue(sequence_->frame_numbers.back());
            aspect_ratio_ = info.width / double(info.height);
            width_->setValue(info.width);
            height_->setValue(info.height);
            if (info.fps)
                fps_->setValue(*info.fps);
            layer_->blockSignals(true);
            layer_->clear();
            for (const auto &name : info.layers)
                layer_->addItem(QString::fromStdString(name));
            layer_->blockSignals(false);
            columns_->setValue(
                std::max(1, static_cast<int>(std::ceil(std::sqrt(info.layers.size())))));
            timeline_->setEnabled(true);
            timeline_->setRange(0, static_cast<int>(sequence_->frame_numbers.size()) - 1);
            timeline_->setValue(0);
            timeline_start_->setText(QString::number(sequence_->frame_numbers.front()));
            timeline_end_->setText(QString::number(sequence_->frame_numbers.back()));
            timeline_current_->setText(QString("Frame: %1").arg(sequence_->frame_numbers.front()));
            const auto stem = derive_sequence_stem(pattern_text.toStdString());
            output_->setText(QString::fromStdString(
                path_to_utf8(sequence_->base_path / path_from_utf8(stem + ".mp4"))));
            request_preview();
        });
    connect(worker, &FileInfoWorker::info_failed, this, [this, generation](const QString &error) {
        if (generation != sequence_generation_)
            return;
        log_->appendPlainText("Sequence error: " + error);
        sequence_.reset();
        timeline_->setEnabled(false);
        preview_->set_message("Preview");
        set_validation_state(input_, "invalid");
        sequence_info_->setText(error);
    });
    connect(worker, &QThread::finished, worker, &QObject::deleteLater);
    worker->start();
    info_workers_.erase(std::remove_if(info_workers_.begin(), info_workers_.end(),
                                       [](const auto &item) { return item.isNull(); }),
                        info_workers_.end());
}
void MainWindow::request_preview(bool scrubbing) {
    if (!sequence_ || sequence_->frame_numbers.empty())
        return;
    const auto generation = ++preview_generation_;
    if (current_preview_ && current_preview_->isRunning()) {
        disconnect(current_preview_, &PreviewWorker::preview_ready, this, nullptr);
        disconnect(current_preview_, &PreviewWorker::preview_failed, this, nullptr);
        preview_pending_ = true;
        return;
    }
    const auto frame = sequence_->frame_numbers.at(static_cast<std::size_t>(timeline_->value()));
    FramePreparationOptions options;
    options.frame_path = sequence_->get_file_path(frame);
    options.ocio_config = ocio_path();
    options.layer = layer_->currentText().toStdString();
    const auto preview_path = QString::fromStdString(path_to_utf8(options.frame_path));
    options.preset = static_cast<ColorSpacePreset>(color_->currentData().toInt());
    if (options.preset == ColorSpacePreset::OcioConversion)
        options.input_space = color_->currentData(Qt::UserRole + 1).toString().toStdString();
    options.output_scale = preview_scale_->value() / 100.0;
    if (sheet_->isChecked() && !scrubbing)
        options.contact_sheet = contact_sheet_config();
    if (burnin_->isChecked() && !scrubbing) {
        options.burnin = burnin_config();
        for (auto &element : options.burnin->elements) {
            element.font_size =
                std::max(1, static_cast<int>(std::round(element.font_size * options.output_scale)));
            if (element.x)
                element.x = static_cast<int>(std::round(element.x * options.output_scale));
            if (element.y)
                element.y = static_cast<int>(std::round(element.y * options.output_scale));
        }
    }
    options.metadata = {frame, path_to_utf8(options.frame_path.filename()), fps_->value(),
                        layer_->currentText().toStdString(), options.input_space.value_or("")};
    auto *worker = new PreviewWorker(std::move(options), this);
    current_preview_ = worker;
    previews_.append(worker);
    connect(worker, &PreviewWorker::preview_ready, this,
            [this, preview_path, generation](const QImage &image) {
                if (generation != preview_generation_)
                    return;
                preview_->set_source_path(preview_path);
                preview_->set_image(image);
            });
    connect(worker, &PreviewWorker::preview_failed, this, [this, generation](const QString &error) {
        if (generation == preview_generation_) {
            preview_->set_message(error);
            log_->appendPlainText("Preview error: " + error);
        }
    });
    connect(worker, &QThread::finished, this, [this, worker] {
        if (current_preview_ == worker) {
            current_preview_ = nullptr;
            if (preview_pending_) {
                preview_pending_ = false;
                request_preview(scrubbing_);
            }
        }
    });
    connect(worker, &QThread::finished, worker, &QObject::deleteLater);
    worker->start();
    previews_.erase(std::remove_if(previews_.begin(), previews_.end(),
                                   [](const auto &item) { return item.isNull(); }),
                    previews_.end());
}
void MainWindow::update_output_actions() {
    const auto path = output_->text().trimmed();
    const auto info = QFileInfo(path);
    const bool available = !path.isEmpty() && info.exists() && info.isFile();
    play_output_->setEnabled(available);
    open_output_->setEnabled(available);
}
void MainWindow::open_output(bool folder) {
    const QFileInfo file(output_->text().trimmed());
    if (!file.exists() || !file.isFile()) {
        update_output_actions();
        QMessageBox::warning(this, "File Not Found",
                             "Output file does not exist:\n" + file.absoluteFilePath());
        return;
    }
    const auto path = folder ? file.absolutePath() : file.absoluteFilePath();
    if (!QDesktopServices::openUrl(QUrl::fromLocalFile(path)))
        QMessageBox::warning(this, "Error", "Could not open:\n" + path);
}
void MainWindow::start_conversion() {
    if (conversion_)
        return;
    try {
        if (!sequence_)
            throw ConfigurationError("Choose an image sequence first");
        const auto [valid, error] = validate_output_filename(output_->text().toStdString());
        if (!valid)
            throw ConfigurationError(error);
        if (!overwrite_->isChecked() && QFileInfo::exists(output_->text()))
            throw ConfigurationError("Output file already exists");
        ConversionConfig config;
        config.input_pattern = input_->currentText().toStdString();
        config.output_path = output_->text().toStdString();
        config.fps = keep_fps_->isChecked() && source_fps_ ? source_fps_
                                                           : std::optional<double>(fps_->value());
        if (!keep_range_->isChecked()) {
            config.start_frame = start_->value();
            config.end_frame = end_->value();
        }
        if (!keep_resolution_->isChecked()) {
            config.width = width_->value();
            config.height = height_->value();
        }
        config.layer = layer_->currentText().toStdString();
        config.color_space_preset = static_cast<ColorSpacePreset>(color_->currentData().toInt());
        if (config.color_space_preset == ColorSpacePreset::OcioConversion)
            config.explicit_input_color_space =
                color_->currentData(Qt::UserRole + 1).toString().toStdString();
        else if (config.color_space_preset == ColorSpacePreset::LinearToSrgb)
            config.explicit_input_color_space = "";
        config.codec = codec_->currentData().toString().toStdString();
        config.quality = quality_->value();
        config.prefetch_workers = workers_->value();
        if (burnin_->isChecked())
            config.burnin_config = burnin_config();
        if (sheet_->isChecked()) {
            config.contact_sheet_mode = true;
            config.contact_sheet_config = contact_sheet_config();
        }
        config.validate();
        auto *worker = new ConversionWorker(std::move(config), ocio_path(), this);
        log_->appendPlainText("Conversion started: " + output_->text());
        conversion_ = worker;
        convert_->setEnabled(false);
        connect(worker, &ConversionWorker::progress_changed, this, [this](int current, int total) {
            progress_->setMaximum(total);
            progress_->setValue(current);
            progress_label_->setText(QString("%1 / %2").arg(current).arg(total));
        });
        connect(worker, &ConversionWorker::conversion_finished, this, [this](const QString &path) {
            progress_label_->setText("Conversion complete");
            log_->appendPlainText("Conversion complete: " + path);
            update_output_actions();
        });
        connect(worker, &ConversionWorker::conversion_failed, this, [this](const QString &error) {
            progress_label_->setText("Conversion failed");
            log_->appendPlainText("Conversion failed: " + error);
            QMessageBox::warning(this, "Conversion failed", error);
        });
        connect(worker, &ConversionWorker::conversion_cancelled, this, [this] {
            progress_label_->setText("Conversion cancelled");
            log_->appendPlainText("Conversion cancelled");
        });
        connect(worker, &QThread::finished, this, [this] {
            conversion_ = nullptr;
            convert_->setEnabled(true);
        });
        connect(worker, &QThread::finished, worker, &QObject::deleteLater);
        worker->start();
    } catch (const std::exception &error) {
        log_->appendPlainText("Cannot convert: " + QString::fromUtf8(error.what()));
        QMessageBox::warning(this, "Cannot convert", QString::fromUtf8(error.what()));
    }
}
void MainWindow::save_settings() {
    QSettings settings("RenderKit", "RenderKit");
    const QList<std::pair<QString, QSpinBox *>> integers{{"width", width_},
                                                         {"height", height_},
                                                         {"prefetch_workers", workers_},
                                                         {"preview_scale", preview_scale_},
                                                         {"burnin_font_size", font_size_},
                                                         {"burnin_opacity", opacity_},
                                                         {"cs_columns", columns_},
                                                         {"cs_padding", padding_}};
    for (const auto &[key, widget] : integers)
        settings.setValue(key, widget->value());
    const QList<std::pair<QString, QCheckBox *>> booleans{
        {"keep_source_fps", keep_fps_},        {"keep_source_frame_range", keep_range_},
        {"keep_resolution", keep_resolution_}, {"burnin_enable", burnin_},
        {"burnin_frame", burnin_frame_},       {"burnin_layer", burnin_layer_},
        {"burnin_fps", burnin_fps_},           {"cs_enable", sheet_}};
    for (const auto &[key, widget] : booleans)
        settings.setValue(key, widget->isChecked());
    settings.setValue("quality", quality_->value());
    settings.setValue("aspect_linked", aspect_link_->isChecked());
    settings.setValue("fps", fps_->value());
    settings.setValue("codec_text", codec_->currentText());
}
void MainWindow::restore_settings() {
    QSettings settings("RenderKit", "RenderKit");
    QSignalBlocker width_blocker(width_), height_blocker(height_);
    const QList<std::pair<QString, QSpinBox *>> integers{{"width", width_},
                                                         {"height", height_},
                                                         {"prefetch_workers", workers_},
                                                         {"preview_scale", preview_scale_},
                                                         {"burnin_font_size", font_size_},
                                                         {"burnin_opacity", opacity_},
                                                         {"cs_columns", columns_},
                                                         {"cs_padding", padding_}};
    for (const auto &[key, widget] : integers)
        if (settings.contains(key))
            widget->setValue(settings.value(key).toInt());
    const QList<std::pair<QString, QCheckBox *>> booleans{
        {"keep_source_fps", keep_fps_},        {"keep_source_frame_range", keep_range_},
        {"keep_resolution", keep_resolution_}, {"burnin_enable", burnin_},
        {"burnin_frame", burnin_frame_},       {"burnin_layer", burnin_layer_},
        {"burnin_fps", burnin_fps_},           {"cs_enable", sheet_}};
    for (const auto &[key, widget] : booleans)
        if (settings.contains(key))
            widget->setChecked(settings.value(key).toBool());
    quality_->setValue(settings.value("quality", 10).toInt());
    aspect_link_->setChecked(settings.value("aspect_linked", true).toBool());
    aspect_ratio_ = width_->value() / double(height_->value());
    fps_->setValue(settings.value("fps", 24).toDouble());
    codec_->setCurrentText(settings.value("codec_text", codec_->currentText()).toString());
    const auto recent = settings.value("recent_patterns").toStringList();
    input_->addItems(recent);
    if (!recent.isEmpty())
        input_->addItem("Clear recent patterns", "clear_recent");
    input_->setEditText("");
}
void MainWindow::closeEvent(QCloseEvent *event) {
    if (conversion_ && QMessageBox::question(this, "Cancel conversion?",
                                             "A conversion is running. Cancel it and close?") !=
                           QMessageBox::Yes) {
        event->ignore();
        return;
    }
    if (conversion_) {
        conversion_->cancel();
        conversion_->wait();
    }
    save_settings();
    event->accept();
}
void MainWindow::dragEnterEvent(QDragEnterEvent *event) {
    const auto urls = event->mimeData()->urls();
    if (std::any_of(urls.begin(), urls.end(), [](const QUrl &url) { return url.isLocalFile(); })) {
        drop_overlay_->setGeometry(rect());
        drop_overlay_->show();
        drop_overlay_->raise();
        event->acceptProposedAction();
    }
}
void MainWindow::dragLeaveEvent(QDragLeaveEvent *event) {
    drop_overlay_->hide();
    event->accept();
}
void MainWindow::resizeEvent(QResizeEvent *event) {
    QMainWindow::resizeEvent(event);
    if (drop_overlay_)
        drop_overlay_->setGeometry(rect());
    if (!splitter_ || !preview_ || !preview_splitter_)
        return;
    const auto height = event->size().height();
    preview_->setVisible(height >= 900);
    splitter_->setSizes(height < 900    ? QList<int>{800, 200}
                        : height < 1100 ? QList<int>{700, 300}
                                        : QList<int>{650, 350});
    preview_splitter_->setSizes(height < 1100 ? QList<int>{400, 180} : QList<int>{450, 250});
}
void MainWindow::dropEvent(QDropEvent *event) {
    drop_overlay_->hide();
    const auto urls = event->mimeData()->urls();
    if (urls.isEmpty())
        return;
    if (urls.size() == 1 && urls.front().isLocalFile() &&
        QFileInfo(urls.front().toLocalFile()).isFile()) {
        const auto path = path_from_utf8(urls.front().toLocalFile().toStdString());
        if (supported_image(path))
            load_sequence(urls.front().toLocalFile());
        else
            sequence_info_->setText("Drop a supported image sequence");
        event->acceptProposedAction();
        return;
    }
    std::map<std::string, std::set<std::filesystem::path>> groups;
    bool has_directory = false;
    auto collect = [&groups](const std::filesystem::path &path) {
        if (supported_image(path))
            if (auto pattern = build_pattern_from_path(path))
                groups[*pattern].insert(path.lexically_normal());
    };
    for (const auto &url : urls) {
        if (!url.isLocalFile())
            continue;
#ifdef Q_OS_WIN
        const std::filesystem::path path(url.toLocalFile().toStdWString());
#else
        const std::filesystem::path path(url.toLocalFile().toStdString());
#endif
        std::error_code ec;
        if (std::filesystem::is_directory(path, ec)) {
            has_directory = true;
            for (std::filesystem::directory_iterator it(path, ec), end; !ec && it != end;
                 it.increment(ec))
                if (it->is_regular_file(ec))
                    collect(it->path());
        } else
            collect(path);
    }
    auto best = std::max_element(groups.begin(), groups.end(), [](const auto &a, const auto &b) {
        return a.second.size() < b.second.size();
    });
    if (best != groups.end() && (has_directory || best->second.size() >= 2))
        load_sequence(QString::fromStdString(best->first));
    else
        sequence_info_->setText(has_directory ? "No supported numbered images found"
                                              : "No sequence with at least two frames found");
    event->acceptProposedAction();
}
} // namespace rk
