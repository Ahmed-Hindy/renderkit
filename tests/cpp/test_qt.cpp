#include "ui/collapsible_group.hpp"
#include <QSignalSpy>
#include <QTest>
#include <QToolButton>

class WidgetTest : public QObject {
    Q_OBJECT
  private slots:
    void headerTogglesContent() {
        rk::CollapsibleGroup group("Settings", false);
        group.resize(300, 100);
        group.show();
        auto *header = group.findChild<QToolButton *>("CollapsibleHeader");
        QVERIFY(header);
        QSignalSpy toggled(header, &QToolButton::toggled);
        QTest::mouseClick(header, Qt::LeftButton);
        QVERIFY(group.is_expanded());
        QCOMPARE(toggled.size(), 1);
        QTest::mouseClick(header, Qt::LeftButton);
        QVERIFY(!group.is_expanded());
        QCOMPARE(toggled.size(), 2);
    }
};
QTEST_MAIN(WidgetTest)
#include "test_qt.moc"
