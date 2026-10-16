import QtQuick
import QtQuick3D

Item {
    id: root
    property string activity: assistantState
    property int wordSerial: assistantWordSerial
    property bool animating: assistantVisible
    property real mouthOpen: 0
    property real eyesOpen: 1
    onWordSerialChanged: if (activity === "speaking" && animating) mouthPulse.restart()
    onActivityChanged: if (activity !== "speaking") { mouthPulse.stop(); mouthOpen = 0 }
    SequentialAnimation {
        id: mouthPulse
        NumberAnimation { target: root; property: "mouthOpen"; to: 1; duration: 60 }
        PauseAnimation { duration: 80 }
        NumberAnimation { target: root; property: "mouthOpen"; to: 0; duration: 130 }
    }
    SequentialAnimation on eyesOpen {
        running: root.animating
        loops: Animation.Infinite
        PauseAnimation { duration: 3600 }
        NumberAnimation { to: 0.12; duration: 90 }
        NumberAnimation { to: 1; duration: 120 }
    }
    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "#0b1420"
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.Medium
        }
        PerspectiveCamera { position: Qt.vector3d(0, 50, 390); fieldOfView: 36 }
        DirectionalLight { eulerRotation: Qt.vector3d(-30, -35, 0); brightness: 1.5; color: "#c3fff2" }
        DirectionalLight { eulerRotation: Qt.vector3d(-10, 150, 0); brightness: 0.7; color: "#efd1a0" }
        Node {
            id: character
            property real angle: 0
            eulerRotation.y: angle
            SequentialAnimation on angle {
                running: root.animating
                loops: Animation.Infinite
                NumberAnimation { to: -7; duration: 2800; easing.type: Easing.InOutSine }
                NumberAnimation { to: 7; duration: 3600; easing.type: Easing.InOutSine }
            }
            Model { source: "#Sphere"; position: Qt.vector3d(0,-34,0); scale: Qt.vector3d(0.88,0.86,0.42); materials: PrincipledMaterial { baseColor: "#173d48"; roughness: 0.75 } }
            Model { source: "#Cylinder"; position: Qt.vector3d(0,24,0); scale: Qt.vector3d(0.24,0.34,0.24); materials: PrincipledMaterial { baseColor: "#a66c48"; roughness: 0.8 } }
            Model { source: "#Sphere"; position: Qt.vector3d(0,65,0); scale: Qt.vector3d(0.51,0.66,0.43); materials: PrincipledMaterial { baseColor: "#b17b54"; roughness: 0.85 } }
            Model { source: "#Sphere"; position: Qt.vector3d(0,42,15); scale: Qt.vector3d(0.44,0.43,0.31); materials: PrincipledMaterial { baseColor: "#211e24"; roughness: 0.95 } }
            // Layered turban silhouette: original geometry, no artist likeness asset.
            Repeater3D {
                model: 5
                delegate: Model {
                    required property int index
                    source: "#Sphere"
                    position: Qt.vector3d(0, 96 + index * 5, -2)
                    scale: Qt.vector3d(0.57 - index*0.035, 0.19, 0.47 - index*0.02)
                    eulerRotation.z: index % 2 === 0 ? 10 : -10
                    materials: PrincipledMaterial { baseColor: index % 2 === 0 ? "#208d87" : "#176b70"; roughness: 0.7 }
                }
            }
            Repeater3D {
                model: 2
                delegate: Node {
                    required property int index
                    position: Qt.vector3d(index === 0 ? -16 : 16, 73, 38)
                    Model { source: "#Sphere"; scale: Qt.vector3d(0.09, 0.045 * root.eyesOpen, 0.04); materials: PrincipledMaterial { baseColor: "#f7ecdb" } }
                    Model { source: "#Sphere"; z: 3; scale: Qt.vector3d(0.035, 0.041 * root.eyesOpen, 0.025); materials: PrincipledMaterial { baseColor: "#342521" } }
                    Model { source: "#Sphere"; y: 8; scale: Qt.vector3d(0.11,0.025,0.025); materials: PrincipledMaterial { baseColor: "#211e24" } }
                }
            }
            Model { source: "#Sphere"; position: Qt.vector3d(0,61,42); scale: Qt.vector3d(0.07,0.12,0.07); materials: PrincipledMaterial { baseColor: "#bd875e" } }
            Model { source: "#Sphere"; position: Qt.vector3d(0,48,42); scale: Qt.vector3d(0.15,0.045,0.035); materials: PrincipledMaterial { baseColor: "#211e24" } }
            Model { source: "#Sphere"; position: Qt.vector3d(0,40,44); scale: Qt.vector3d(0.1,0.014 + root.mouthOpen*0.045,0.025); materials: PrincipledMaterial { baseColor: "#160f17" } }
            Model { source: "#Cylinder"; position: Qt.vector3d(0,-91,0); scale: Qt.vector3d(1.1,0.07,0.6); materials: PrincipledMaterial { baseColor: root.activity === "error" ? "#fa795e" : "#39dfc4"; metalness: 0.5; roughness: 0.3 } }
        }
    }
    Text { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; text: "ORIGINAL CHARACTER  ·  " + root.activity.toUpperCase(); color: "#8bdfd1"; font.pixelSize: 12 }
}
