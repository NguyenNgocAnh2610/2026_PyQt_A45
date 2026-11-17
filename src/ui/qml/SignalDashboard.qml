import QtQuick
import QtQuick.Controls

// Signal dashboard. Colours follow assets/styles/main.qss (dark navy theme).
// Live values are cyan; a value kept after its test shows the verdict colour,
// a chip (PASS/FAIL/…) and "test/step · time" so it is never read as current.
Rectangle {
    id: dashboard
    color: "#111f31"
    clip: true
    property int measurementCount: 0
    readonly property color idleColor: "#5f758a"

    component Led: Item {
        id: led
        property color tone: dashboard.idleColor
        property bool active: false
        width: 22; height: 22
        Rectangle {
            id: halo
            anchors.centerIn: parent
            width: 22; height: 22; radius: 11
            color: led.tone
            opacity: led.active ? 0.28 : 0
            SequentialAnimation on opacity {
                running: led.active
                loops: Animation.Infinite
                NumberAnimation { to: 0.08; duration: 900; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.32; duration: 900; easing.type: Easing.InOutSine }
            }
        }
        Rectangle {
            anchors.centerIn: parent
            width: 12; height: 12; radius: 6
            color: led.active ? led.tone : "#2a3b4e"
            border.width: 1
            border.color: led.active ? Qt.lighter(led.tone, 1.4) : "#4a5f74"
        }
    }

    component VerdictChip: Item {
        id: chip
        property string text: ""
        property color tone: dashboard.idleColor
        visible: text.length > 0
        width: chipLabel.implicitWidth + 14
        height: 18
        Rectangle { anchors.fill: parent; radius: 9; color: chip.tone; opacity: 0.18 }
        Rectangle { anchors.fill: parent; radius: 9; color: "transparent"; border.width: 1; border.color: chip.tone; opacity: 0.55 }
        Text {
            id: chipLabel
            anchors.centerIn: parent
            text: chip.text
            color: chip.tone
            font.family: "Segoe UI"
            font.pixelSize: 11
            font.weight: Font.Bold
        }
    }

    component SignalCard: Rectangle {
        id: card
        required property string label
        required property string group
        required property string kind
        required property string display
        required property string unit
        required property string quality
        required property string stateColor
        required property bool highlight
        required property bool cardVisible
        required property bool pinned
        required property string sourceLabel
        required property string subtitle
        required property string verdict
        required property bool live
        required property bool recorded
        readonly property bool hasValue: live || recorded
        height: pinned ? 58 : 74
        radius: 10
        gradient: Gradient {
            GradientStop { position: 0.0; color: card.highlight ? "#1a3550" : "#16293e" }
            GradientStop { position: 1.0; color: card.highlight ? "#142c42" : "#122236" }
        }
        border.width: 1
        border.color: hover.hovered ? "#3f7593" : (card.highlight ? "#2d6380" : "#22384f")
        Behavior on border.color { ColorAnimation { duration: 150 } }
        HoverHandler { id: hover }
        ToolTip.visible: hover.hovered
        ToolTip.delay: 350
        ToolTip.text: label + "\n" + display + " " + unit + "\n" + group + " · " + quality + " · " + sourceLabel
                      + (recorded && !live ? "\nGiá trị đã lưu: " + subtitle + (verdict ? " · " + verdict : "") : "")

        // Accent bar: verdict/live colour, dim when there is no value.
        Rectangle {
            visible: !card.pinned
            x: 0; y: 10
            width: 4; height: parent.height - 20; radius: 2
            color: card.hasValue ? card.stateColor : "#2a3d52"
        }
        Led {
            visible: card.pinned
            x: 12
            anchors.verticalCenter: parent.verticalCenter
            tone: card.stateColor
            active: card.live
        }
        Column {
            x: card.pinned ? 44 : 16
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - valueRow.width - 24
            spacing: 4
            Text {
                width: parent.width
                text: card.label
                elide: Text.ElideRight
                font.family: "Segoe UI"
                font.pixelSize: 16
                font.weight: Font.DemiBold
                color: "#dbe8f4"
            }
            Row {
                spacing: 6
                width: parent.width
                VerdictChip {
                    id: verdictChip
                    text: card.recorded && !card.live ? card.verdict : ""
                    tone: card.stateColor
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    width: parent.width - (verdictChip.visible ? verdictChip.width + parent.spacing : 0)
                    text: card.subtitle
                    elide: Text.ElideRight
                    font.family: "Segoe UI"
                    font.pixelSize: 13
                    color: card.live ? "#8fb7cc" : (card.recorded ? "#a9bccd" : "#c9a874")
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
        Row {
            id: valueRow
            anchors.right: parent.right
            anchors.rightMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Text {
                id: valueText
                text: card.display
                width: card.kind === "number" ? Math.min(implicitWidth, 120)
                                              : Math.min(implicitWidth, card.width * 0.5)
                elide: Text.ElideRight
                color: card.hasValue ? card.stateColor : "#4f6479"
                font.family: "Segoe UI"
                font.pixelSize: card.pinned ? 18 : (card.kind === "number" ? 26 : 18)
                font.weight: Font.Bold
            }
            Text {
                visible: !card.pinned && card.kind === "number"
                text: card.unit
                color: "#8fa9bf"
                font.family: "Segoe UI"
                font.pixelSize: 15
                anchors.baseline: valueText.baseline
            }
        }
    }

    Column {
        anchors.fill: parent
        spacing: 10
        Flow {
            id: statusFlow
            width: parent.width
            property int columns: Math.max(1, Math.min(statusCount, Math.floor((width + 10) / 240)))
            spacing: 10
            Repeater {
                model: benchSignals
                delegate: SignalCard {
                    visible: pinned
                    width: (statusFlow.width - (statusFlow.columns - 1) * 10) / statusFlow.columns
                }
            }
        }
        Flickable {
            id: scroller
            width: parent.width
            height: Math.max(0, parent.height - statusFlow.height - 10)
            clip: true
            contentWidth: width
            contentHeight: rows.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            Text {
                visible: dashboard.measurementCount === 0
                anchors.centerIn: parent
                text: "Không có tín hiệu phù hợp bộ lọc"
                color: "#8faabd"
                font.pixelSize: 16
            }
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                contentItem: Rectangle { implicitWidth: 6; radius: 3; color: "#426179" }
                background: Rectangle { color: "#111f31" }
            }
            Flow {
                id: rows
                width: scroller.width - 10
                property int columns: Math.max(1, Math.min(dashboard.measurementCount, Math.floor((width + 10) / 300)))
                spacing: 10
                Repeater {
                    model: benchSignals
                    delegate: SignalCard {
                        visible: !pinned && cardVisible
                        width: (rows.width - (rows.columns - 1) * 10) / rows.columns
                    }
                }
            }
        }
    }
}
