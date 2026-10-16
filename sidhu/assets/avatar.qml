import QtQuick
import QtQuick3D

// Original, articulated low-poly tribute character. No imported likeness asset.
// Animation state and mouth positions are received from the actual application.
Item {
    id: root
    property string activity: assistantState
    property int wordSerial: assistantWordSerial
    property bool animating: assistantVisible
    property bool lightweight: typeof assistantLightweight === "undefined" ? false : assistantLightweight
    property int viseme: typeof assistantViseme === "undefined" ? 0 : assistantViseme
    property int visemeSerial: typeof assistantVisemeSerial === "undefined" ? 0 : assistantVisemeSerial
    property int visemeDuration: typeof assistantVisemeDuration === "undefined" ? 100 : assistantVisemeDuration
    property real phase: 0
    property real mouthOpen: 0
    property real mouthWidth: 1
    property real mouthRound: 0
    property real eyesOpen: 1
    property real mouthUntil: 0
    property real nativeUntil: 0
    property bool listening: activity === "listening" || activity === "loading" || activity === "recovering"
    property bool thinking: activity === "thinking" || activity === "working" || activity === "processing"
    property bool speaking: activity === "speaking"
    property real breath: lightweight ? 0 : Math.sin(phase * 1.3) * 1.1
    property real gesture: speaking && !lightweight ? Math.sin(phase * 1.7) : 0
    property string lipSyncMode: "idle"
    function receiveViseme() {
        if (!speaking || viseme < 0 || viseme > 21) return
        const aperture = [0,.60,.82,.62,.44,.52,.26,.34,.60,.60,.62,.66,.20,.23,.24,.22,.38,.36,.18,.27,.18,0]
        const width = [1,1.04,.9,.78,1.1,1.1,1.2,.7,.72,1.02,.76,1.1,.95,1.04,1.08,.94,.85,.95,1.04,1,.96,.9]
        mouthOpen = aperture[viseme]
        mouthWidth = width[viseme]
        mouthRound = viseme === 7 || viseme === 8 || viseme === 10 ? .9 : .1
        mouthUntil = Date.now() + Math.max(20, Math.min(1500, visemeDuration))
        nativeUntil = Date.now() + 1500
        lipSyncMode = "viseme"
    }
    onVisemeSerialChanged: receiveViseme()
    onWordSerialChanged: {
        if (speaking && Date.now() > nativeUntil) {
            mouthOpen = .34 + (wordSerial % 3) * .10
            mouthWidth = 1
            mouthRound = .1
            mouthUntil = Date.now() + 180
            lipSyncMode = "word approximation"
        }
    }
    onActivityChanged: {
        // Read activity directly: the derived speaking binding can still hold
        // its previous value while this change handler is being delivered.
        if (activity !== "speaking") { mouthOpen = 0; mouthUntil = 0; lipSyncMode = "idle" }
    }
    Timer {
        // Scene transforms change at <=30 Hz; idle animation stops when hidden.
        interval: root.lightweight ? 100 : 34
        running: root.animating
        repeat: true
        onTriggered: {
            if (!root.lightweight) root.phase += interval / 1000
            const blink = root.phase % 4.9
            root.eyesOpen = blink < 4.67 ? 1 : Math.max(.06, Math.abs(blink - 4.785) / .115)
            if (Date.now() > root.mouthUntil) root.mouthOpen = 0
        }
    }
    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: root.lightweight ? SceneEnvironment.NoAA : SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.Medium
        }
        PerspectiveCamera { position: Qt.vector3d(0, 20, 480); fieldOfView: 40; clipNear: 5; clipFar: 900 }
        DirectionalLight { eulerRotation: Qt.vector3d(-28,-25,0); brightness: 1.8; color: "#ffe4c3" }
        DirectionalLight { eulerRotation: Qt.vector3d(-10,125,0); brightness: 1.25; color: "#199de9" }
        PointLight { position: Qt.vector3d(150,110,80); brightness: 2.5; color: "#ffc18a"; quadraticFade: 0.05 }
        PrincipledMaterial { id: skin; baseColor: "#c58a60"; roughness: .68; specularAmount: .22 }
        PrincipledMaterial { id: skinLight; baseColor: "#db9f71"; roughness: .65 }
        PrincipledMaterial { id: jacket; baseColor: "#101c2d"; roughness: .64; metalness: .04 }
        PrincipledMaterial { id: clothDark; baseColor: "#080e1a"; roughness: .87 }
        PrincipledMaterial { id: clothFold; baseColor: "#172337"; roughness: .83 }
        PrincipledMaterial { id: beard; baseColor: "#211d1e"; roughness: .96 }
        PrincipledMaterial { id: cyan; baseColor: "#42cfff"; emissiveFactor: Qt.vector3d(.04,.45,.85); roughness: .3 }
        PrincipledMaterial { id: steel; baseColor: "#718397"; metalness: .8; roughness: .3 }
        PrincipledMaterial { id: whiteEye; baseColor: "#e9d8be"; roughness: .46 }
        PrincipledMaterial { id: iris; baseColor: "#4a2d20"; roughness: .3 }
        PrincipledMaterial { id: pupil; baseColor: "#0b0c12"; roughness: .2 }
        PrincipledMaterial { id: lips; baseColor: "#a86a59"; roughness: .7 }
        PrincipledMaterial { id: mouthInside; baseColor: "#230f19"; roughness: 1 }
        PrincipledMaterial { id: teeth; baseColor: "#dcc8ad"; roughness: .7 }
        Node {
            id: character
            y: root.breath - 4
            eulerRotation.y: root.lightweight ? 0 : Math.sin(root.phase*.32)*2.2
            // Half-body jacket, collar and shoulders.
            Model { source: "#Sphere"; position: Qt.vector3d(0,-66,0); scale: Qt.vector3d(1.43,1.32,.68); materials: jacket }
            Model { source: "#Sphere"; position: Qt.vector3d(0,-126,-3); scale: Qt.vector3d(1.32,.45,.65); materials: clothDark }
            Model { source: "#Sphere"; position: Qt.vector3d(-47,-6,0); scale: Qt.vector3d(.62,.5,.62); eulerRotation.z: -22; materials: jacket }
            Model { source: "#Sphere"; position: Qt.vector3d(47,-6,0); scale: Qt.vector3d(.62,.5,.62); eulerRotation.z: 22; materials: jacket }
            Model { source: "#Cylinder"; position: Qt.vector3d(0,33,0); scale: Qt.vector3d(.34,.48,.32); materials: skin }
            Model { source: "#Sphere"; position: Qt.vector3d(-19,8,14); scale: Qt.vector3d(.5,.65,.3); eulerRotation.z: 30; materials: clothDark }
            Model { source: "#Sphere"; position: Qt.vector3d(19,8,14); scale: Qt.vector3d(.5,.65,.3); eulerRotation.z: -30; materials: clothFold }
            Model { source: "#Cylinder"; position: Qt.vector3d(0,-73,34); scale: Qt.vector3d(.018,1.1,.018); materials: steel }
            Repeater3D {
                model: 2
                delegate: Node {
                    required property int index
                    x: index === 0 ? -39 : 39
                    Model { source: "#Cylinder"; position: Qt.vector3d(0,-68,28); scale: Qt.vector3d(.022,.83,.022); eulerRotation.z: index === 0 ? -6 : 6; materials: cyan }
                    Model { source: "#Cylinder"; position: Qt.vector3d(0,-69,29); scale: Qt.vector3d(.009,.83,.009); eulerRotation.z: index === 0 ? -6 : 6; materials: whiteEye }
                }
            }
            // Headphones around the neck: original geometry and lit ear cups.
            Repeater3D {
                model: 2
                delegate: Node {
                    required property int index
                    position: Qt.vector3d(index === 0 ? -32 : 32, 20, 23)
                    eulerRotation.z: index === 0 ? -23 : 23
                    Model { source: "#Cylinder"; scale: Qt.vector3d(.30,.16,.40); eulerRotation.x: 90; materials: clothDark }
                    Model { source: "#Cylinder"; z: 9; scale: Qt.vector3d(.24,.025,.34); eulerRotation.x: 90; materials: cyan }
                    Model { source: "#Cylinder"; z: 11; scale: Qt.vector3d(.20,.03,.30); eulerRotation.x: 90; materials: jacket }
                    Model { source: "#Cube"; position: Qt.vector3d(0,0,14); scale: Qt.vector3d(.03,.13,.015); eulerRotation.z: 17; materials: cyan }
                }
            }
            Node {
                id: head
                position: Qt.vector3d(0,87,0)
                eulerRotation.x: root.thinking ? -5 : root.speaking && !root.lightweight ? Math.sin(root.phase*1.7)*2 : 0
                eulerRotation.y: root.lightweight ? 0 : Math.sin(root.phase*.43)*3
                eulerRotation.z: root.listening ? -7 : root.thinking ? 4 : -2
                Model { source: "#Sphere"; scale: Qt.vector3d(.65,.85,.58); materials: skin }
                Model { source: "#Sphere"; position: Qt.vector3d(0,-24,4); scale: Qt.vector3d(.62,.46,.52); materials: beard }
                Repeater3D {
                    model: 2
                    delegate: Node {
                        required property int index
                        x: index === 0 ? -32 : 32
                        Model { source: "#Sphere"; position: Qt.vector3d(0,-1,0); scale: Qt.vector3d(.13,.25,.12); materials: skin }
                        Model { source: "#Sphere"; position: Qt.vector3d(index === 0 ? -2 : 2,-2,4); scale: Qt.vector3d(.06,.14,.04); materials: skinLight }
                    }
                }
                // Black wrapped turban; cloth folds cross diagonally at the front.
                Model { source: "#Sphere"; position: Qt.vector3d(0,38,-2); scale: Qt.vector3d(.90,.64,.70); materials: clothDark }
                Repeater3D {
                    model: 8
                    delegate: Model {
                        required property int index
                        source: "#Sphere"
                        position: Qt.vector3d((index%2 === 0 ? -3 : 3), 29+index*4, 1)
                        scale: Qt.vector3d(.85-index*.025,.14,.70-index*.015)
                        eulerRotation.z: index%2 === 0 ? 22 : -22
                        materials: index%3 === 0 ? clothFold : clothDark
                    }
                }
                Repeater3D {
                    model: 2
                    delegate: Node {
                        required property int index
                        position: Qt.vector3d(index === 0 ? -13.5 : 13.5, 11.5, 26)
                        Model { source: "#Sphere"; scale: Qt.vector3d(.16,.066*root.eyesOpen,.045); materials: whiteEye }
                        Model { source: "#Sphere"; position: Qt.vector3d(0,0,2); scale: Qt.vector3d(.064,.064*root.eyesOpen,.025); materials: iris }
                        Model { source: "#Sphere"; position: Qt.vector3d(0,0,3.2); scale: Qt.vector3d(.032,.048*root.eyesOpen,.02); materials: pupil }
                        Model { source: "#Sphere"; position: Qt.vector3d(-1,1,4); scale: Qt.vector3d(.012,.014*root.eyesOpen,.008); materials: whiteEye }
                        Model { source: "#Sphere"; y: root.thinking && index === 0 ? 11 : 9; scale: Qt.vector3d(.21,.039,.055); eulerRotation.z: index === 0 ? -10 : 10; materials: beard }
                    }
                }
                Model { source: "#Sphere"; position: Qt.vector3d(0,-1,29); scale: Qt.vector3d(.095,.18,.12); materials: skinLight }
                Model { source: "#Sphere"; position: Qt.vector3d(0,-7,32); scale: Qt.vector3d(.16,.065,.075); materials: skin }
                // Mouth aperture, width and lips come from actual SAPI visemes.
                Model { source: "#Sphere"; position: Qt.vector3d(0,-21,28); scale: Qt.vector3d(.23*root.mouthWidth,.028+root.mouthOpen*.10,.07); materials: lips }
                Model { source: "#Sphere"; position: Qt.vector3d(0,-21,30); scale: Qt.vector3d(.20*root.mouthWidth,.012+root.mouthOpen*.086,.042); materials: mouthInside }
                Model { source: "#Cube"; position: Qt.vector3d(0,-19,32); scale: Qt.vector3d(.15*root.mouthWidth,.018,.009); visible: root.mouthOpen>.23; materials: teeth }
                Repeater3D {
                    model: 2
                    delegate: Model {
                        required property int index
                        source: "#Sphere"
                        position: Qt.vector3d(index === 0 ? -7 : 7,-12,30)
                        scale: Qt.vector3d(.20,.064,.068)
                        eulerRotation.z: index === 0 ? 14 : -14
                        materials: beard
                    }
                }
            }
            // Raised left arm: shoulder, elbow, wrist and individual fingers.
            Node {
                position: Qt.vector3d(-65,-10,0)
                eulerRotation.z: -30
                Model { source: "#Sphere"; y: -25; scale: Qt.vector3d(.43,.69,.44); materials: jacket }
                Node {
                    position: Qt.vector3d(0,-55,0)
                    eulerRotation: Qt.vector3d(-69,0,-104 + root.gesture*4)
                    Model { source: "#Sphere"; y: -24; scale: Qt.vector3d(.34,.62,.35); materials: jacket }
                    Model { source: "#Cylinder"; y: -48; scale: Qt.vector3d(.31,.06,.31); materials: clothDark }
                    Node {
                        position: Qt.vector3d(0,-57,0)
                        eulerRotation: Qt.vector3d(24+root.gesture*3,0,4)
                        Model { source: "#Sphere"; y: -8; scale: Qt.vector3d(.29,.36,.13); materials: skinLight }
                        Repeater3D {
                            model: 4
                            delegate: Node {
                                required property int index
                                position: Qt.vector3d(-10+index*7,-21,0)
                                eulerRotation.z: -12+index*9
                                Model { source: "#Cylinder"; y: -9; scale: Qt.vector3d(.055,.19-index*.015,.056); materials: skin }
                                Model { source: "#Sphere"; y: -18+index*1.5; scale: Qt.vector3d(.056,.065,.056); materials: skinLight }
                            }
                        }
                        Model { source: "#Sphere"; position: Qt.vector3d(-16,-3,1); scale: Qt.vector3d(.09,.25,.09); eulerRotation.z: -48; materials: skin }
                        Model { source: "#Cylinder"; y: 8; scale: Qt.vector3d(.30,.027,.15); materials: steel }
                    }
                }
            }
            // Relaxed right arm and open hand at desk height.
            Node {
                position: Qt.vector3d(65,-10,-1)
                eulerRotation.z: 16
                Model { source: "#Sphere"; y: -35; scale: Qt.vector3d(.44,.82,.44); materials: jacket }
                Node {
                    position: Qt.vector3d(0,-74,0)
                    eulerRotation: Qt.vector3d(-74,0,35)
                    Model { source: "#Sphere"; y: -24; scale: Qt.vector3d(.33,.62,.35); materials: jacket }
                    Model { source: "#Cylinder"; y: -48; scale: Qt.vector3d(.32,.05,.33); materials: clothDark }
                    Node {
                        y: -59
                        Model { source: "#Sphere"; scale: Qt.vector3d(.29,.35,.14); materials: skin }
                        Repeater3D {
                            model: 4
                            delegate: Model {
                                required property int index
                                source: "#Sphere"
                                position: Qt.vector3d(-10+index*7,-22+Math.abs(index-1)*2,2)
                                scale: Qt.vector3d(.065,.24,.068)
                                materials: skinLight
                            }
                        }
                        Model { source: "#Cube"; position: Qt.vector3d(0,17,9); scale: Qt.vector3d(.20,.21,.06); materials: steel }
                        Model { source: "#Cube"; position: Qt.vector3d(0,17,13); scale: Qt.vector3d(.16,.16,.012); materials: pupil }
                    }
                }
            }
        }
    }
}
