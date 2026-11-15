#pragma once
#include "core/sequence.hpp"
#include "workers.hpp"
#include <QMainWindow>
#include <QPointer>
#include <memory>
#include <optional>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QProgressBar;
class QPushButton;
class QSlider;
class QSpinBox;
class QSplitter;
class QTimer;
namespace rk {
class CollapsibleGroup;
class PreviewWidget;
struct UiLogState;
class MainWindow : public QMainWindow {
    Q_OBJECT
  public:
    explicit MainWindow(const QString &initial_path = {}, QWidget *parent = nullptr);
    ~MainWindow() override;

  protected:
    void closeEvent(QCloseEvent *event) override;
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dragLeaveEvent(QDragLeaveEvent *event) override;
    void dropEvent(QDropEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

  private:
    void load_sequence(const QString &path);
    void request_preview(bool scrubbing = false);
    void update_output_actions();
    void open_output(bool folder);
    void start_conversion();
    void save_settings();
    void restore_settings();
    BurnInConfig burnin_config() const;
    ContactSheetConfig contact_sheet_config() const;
    std::filesystem::path ocio_path() const;
    QComboBox *input_, *layer_, *color_, *codec_;
    QLineEdit *output_;
    QLabel *sequence_info_, *progress_label_, *drop_overlay_ = nullptr;
    QLabel *timeline_start_, *timeline_end_, *timeline_current_;
    PreviewWidget *preview_ = nullptr;
    QSpinBox *start_, *end_, *width_, *height_, *workers_, *preview_scale_, *font_size_, *opacity_,
        *columns_, *padding_;
    QDoubleSpinBox *fps_;
    QCheckBox *keep_fps_, *keep_range_, *keep_resolution_, *burnin_, *burnin_frame_, *burnin_layer_,
        *burnin_fps_, *sheet_, *overwrite_;
    QSlider *timeline_, *quality_;
    QProgressBar *progress_;
    QPushButton *convert_;
    QPushButton *aspect_link_;
    QPushButton *play_output_, *open_output_;
    QSplitter *splitter_ = nullptr;
    QSplitter *preview_splitter_ = nullptr;
    QPlainTextEdit *log_ = nullptr;
    std::shared_ptr<UiLogState> log_state_;
    CollapsibleGroup *sheet_group_;
    QTimer *preview_timer_;
    QPointer<ConversionWorker> conversion_;
    QList<QPointer<PreviewWorker>> previews_;
    QPointer<PreviewWorker> current_preview_;
    QList<QPointer<FileInfoWorker>> info_workers_;
    QPointer<FileInfoWorker> current_info_;
    std::optional<FrameSequence> sequence_;
    std::optional<double> source_fps_;
    std::optional<std::string> source_color_;
    bool scrubbing_ = false;
    bool preview_pending_ = false;
    quint64 sequence_generation_ = 0, preview_generation_ = 0;
    double aspect_ratio_ = 1920.0 / 1080.0;
};
} // namespace rk
