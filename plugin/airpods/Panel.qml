import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "airpods"
  ipcTarget: "airpods"
  manageIpc: true

  property var state: Model.emptyState()
  property string airpodsBin: Quickshell.env("HOME") + "/.local/bin/airpods"
  readonly property bool isConnected: state.connected === true
  readonly property bool isCommunicating: state.communicating === true
  readonly property var minLevel: Model.minEarbudLevel(state.battery)
  readonly property color fg: bar ? bar.foreground : Commons.Color.foreground
  readonly property color accentColor: Commons.Color.accent
  readonly property string fontFam: bar ? bar.fontFamily : Style.font.family
  readonly property string iconGlyph: "󰋋"
  readonly property var noiseModes: Model.NOISE_MODE_OPTIONS

  function applyWatchLine(line) {
    var next = Model.parseWatchLine(line)
    if (next) root.state = next
  }

  function resetOnWatchExit() {
    root.state = Model.emptyState()
    if (root.opened) root.close()
    reconnectTimer.restart()
  }

  function setNoiseMode(mode) {
    if (!root.isConnected || !root.isCommunicating || !mode || modeProc.running) return
    modeProc.command = [
      "bash",
      "-lc",
      "if [ -x \"$0\" ]; then exec \"$0\" mode \"$1\"; else exec airpods mode \"$1\"; fi",
      root.airpodsBin,
      String(mode)
    ]
    modeProc.running = true
  }

  function toggleEarDetection() {
    if (earProc.running) return
    var nextVal = root.state.ear_detection ? "off" : "on"
    earProc.command = [
      "bash",
      "-lc",
      "if [ -x \"$0\" ]; then exec \"$0\" ear-detection \"$1\"; else exec airpods ear-detection \"$1\"; fi",
      root.airpodsBin,
      nextVal
    ]
    earProc.running = true
  }

  onIsConnectedChanged: {
    if (!isConnected && opened) close()
  }

  visible: isConnected
  implicitWidth: isConnected ? button.implicitWidth : 0
  implicitHeight: isConnected ? button.implicitHeight : 0

  Process {
    id: watchProc
    command: ["bash", "-lc", "if [ -x \"$0\" ]; then exec \"$0\" watch; else exec airpods watch; fi", root.airpodsBin]
    running: true
    stdout: SplitParser {
      onRead: function(line) { root.applyWatchLine(line) }
    }
    onExited: root.resetOnWatchExit()
  }

  Process {
    id: modeProc
  }

  Process {
    id: earProc
  }

  Timer {
    id: reconnectTimer
    interval: 2000
    repeat: false
    running: false
    onTriggered: {
      if (!watchProc.running) watchProc.running = true
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Model.barLabel(root.state, vertical, root.iconGlyph)
    dimmed: root.isConnected && !root.isCommunicating
    tooltipText: !root.isConnected
      ? ""
      : (!root.isCommunicating
          ? "Sin comunicación con los AirPods"
          : (root.minLevel !== null ? "AirPods · " + root.minLevel + "%" : "AirPods"))
    onPressed: function(b) {
      if (!root.isConnected) return
      root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened && root.isConnected
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(14)

        // ---------- Cabecera ----------
        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroPercent.implicitHeight)

          Text {
            id: heroIcon
            textFormat: Text.PlainText
            text: root.iconGlyph
            color: root.fg
            opacity: root.isCommunicating ? 1.0 : 0.45
            font.family: root.fontFam
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: heroPercent.left
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              textFormat: Text.PlainText
              text: "AirPods"
              color: root.fg
              font.family: root.fontFam
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              textFormat: Text.PlainText
              text: root.isCommunicating ? "CONECTADOS" : "SIN COMUNICACIÓN CON LOS AIRPODS"
              color: Qt.darker(root.fg, 1.4)
              font.family: root.fontFam
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.1
              elide: Text.ElideRight
              width: parent.width
            }
          }

          Text {
            id: heroPercent
            textFormat: Text.PlainText
            text: root.isCommunicating && root.minLevel !== null ? root.minLevel + "%" : "—"
            color: root.fg
            font.family: root.fontFam
            font.pixelSize: Style.font.displayLarge
            font.bold: true
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        // ---------- Aviso sin comunicación ----------
        BorderSurface {
          visible: !root.isCommunicating
          width: parent.width
          implicitHeight: noCommText.implicitHeight + Style.space(16)
          radius: Style.cornerRadius
          color: Style.normalFillFor(root.fg, root.accentColor)
          borderSpec: Border.controlSpec("normal", root.fg, root.accentColor)

          Text {
            id: noCommText
            anchors.centerIn: parent
            width: parent.width - Style.space(20)
            textFormat: Text.PlainText
            text: "Sin comunicación con los AirPods"
            color: root.fg
            font.family: root.fontFam
            font.pixelSize: Style.font.bodySmall
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
          }
        }

        PanelSeparator {
          foreground: root.fg
        }

        // ---------- Batería por pieza ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "BATERÍA"
            foreground: root.fg
            fontFamily: root.fontFam
          }

          PieceRow {
            pieceName: "Auricular izquierdo"
            piece: root.state.battery ? root.state.battery.left : null
          }

          PieceRow {
            pieceName: "Auricular derecho"
            piece: root.state.battery ? root.state.battery.right : null
          }

          PieceRow {
            pieceName: "Estuche"
            piece: root.state.battery ? root.state.battery.case : null
          }
        }

        PanelSeparator {
          foreground: root.fg
        }

        // ---------- Modo de ruido ----------
        Column {
          width: parent.width
          spacing: Style.space(10)
          opacity: root.isCommunicating ? 1.0 : 0.5

          PanelSectionHeader {
            text: "MODO DE RUIDO"
            foreground: root.fg
            fontFamily: root.fontFam
          }

          Grid {
            id: modeGrid
            width: parent.width
            columns: 2
            spacing: Style.space(6)

            readonly property real cellWidth: (width - spacing) / 2

            Repeater {
              model: root.noiseModes

              Button {
                required property var modelData
                width: modeGrid.cellWidth
                text: modelData.label
                fontSize: Style.font.bodySmall
                foreground: root.fg
                accent: root.accentColor
                fontFamily: root.fontFam
                bordered: true
                enabled: root.isCommunicating
                selected: root.state.noise_mode === modelData.value
                onClicked: root.setNoiseMode(modelData.value)
              }
            }
          }
        }

        PanelSeparator {
          foreground: root.fg
        }

        // ---------- Detección de oído ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "DETECCIÓN DE OÍDO"
            foreground: root.fg
            fontFamily: root.fontFam
          }

          Toggle {
            width: parent.width
            label: "Detección de oído"
            description: "Pausa automática al quitarte un auricular"
            checked: root.state.ear_detection === true
            foreground: root.fg
            accent: root.accentColor
            fontFamily: root.fontFam
            onClicked: root.toggleEarDetection()
          }

          Row {
            width: parent.width
            spacing: Style.space(12)

            InEarBadge {
              width: (parent.width - parent.spacing) / 2
              pieceLabel: "Izquierdo"
              inEarValue: root.state.in_ear ? root.state.in_ear.left : null
            }

            InEarBadge {
              width: (parent.width - parent.spacing) / 2
              pieceLabel: "Derecho"
              inEarValue: root.state.in_ear ? root.state.in_ear.right : null
            }
          }
        }
      }
    }
  }

  component PieceRow: Column {
    property string pieceName: ""
    property var piece: null
    readonly property bool known: piece !== null && piece !== undefined && piece.level !== null && piece.level !== undefined
    readonly property real fraction: known ? Math.max(0, Math.min(1, piece.level / 100)) : 0

    width: parent.width
    spacing: Style.space(4)

    Row {
      width: parent.width
      spacing: Style.space(8)

      Text {
        id: nameLabel
        textFormat: Text.PlainText
        text: pieceName
        color: root.fg
        font.family: root.fontFam
        font.pixelSize: Style.font.bodySmall
      }

      Item {
        width: Math.max(0, parent.width - nameLabel.implicitWidth - valueLabel.implicitWidth - parent.spacing * 2)
        height: 1
      }

      Text {
        id: valueLabel
        textFormat: Text.PlainText
        text: Model.formatPieceBattery(piece)
        color: known ? root.fg : Qt.darker(root.fg, 1.45)
        font.family: root.fontFam
        font.pixelSize: Style.font.bodySmall
        font.bold: known
      }
    }

    Item {
      width: parent.width
      implicitHeight: Style.space(6)

      Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)
      }

      Rectangle {
        visible: known
        anchors.left: track.left
        anchors.verticalCenter: track.verticalCenter
        height: track.height
        radius: track.radius
        color: piece && piece.charging ? root.accentColor : root.fg
        width: known ? Math.max(track.height, track.width * fraction) : 0

        Behavior on width { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
      }
    }
  }

  component InEarBadge: BorderSurface {
    property string pieceLabel: ""
    property var inEarValue: null

    implicitHeight: badgeRow.implicitHeight + Style.space(12)
    radius: Style.cornerRadius
    color: inEarValue === true
      ? Style.selectedFillFor(root.fg, root.accentColor)
      : Style.normalFillFor(root.fg, root.accentColor)
    borderSpec: Border.controlSpec(inEarValue === true ? "selected" : "normal", root.fg, root.accentColor)

    Row {
      id: badgeRow
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(6)

      Text {
        id: leftLbl
        textFormat: Text.PlainText
        text: pieceLabel
        color: root.fg
        font.family: root.fontFam
        font.pixelSize: Style.font.bodySmall
      }

      Item {
        width: Math.max(0, parent.width - leftLbl.implicitWidth - rightLbl.implicitWidth - parent.spacing * 2)
        height: 1
      }

      Text {
        id: rightLbl
        textFormat: Text.PlainText
        text: Model.formatInEarPiece(inEarValue)
        color: inEarValue === true ? root.fg : Qt.darker(root.fg, 1.4)
        font.family: root.fontFam
        font.pixelSize: Style.font.bodySmall
        font.bold: inEarValue === true
      }
    }
  }
}
