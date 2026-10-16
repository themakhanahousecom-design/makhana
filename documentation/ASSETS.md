# Interface artwork

The interface uses original artwork created for this project:

| File | Purpose | Origin |
| --- | --- | --- |
| `sidhu/assets/workstation.png` | Dark workstation background | Generated for this redesign; no people, text or UI controls |
| `sidhu/assets/tribute-portrait.png` | Software fallback portrait | Generated fictional Punjabi male character; transparent PNG, no celebrity asset |
| `sidhu/assets/avatar.qml` | Native articulated 3D character | Original procedural geometry, materials and animation code |
| `sidhu/avatar_portrait.py` | Live 2D animation and vector fallback | Original QPainter drawing and speech-driven overlays |
| `sidhu/interface.py` | Crown, icons, glass panels and lighting | Original vector drawing and Qt widgets |

The rendered portrait is used by **ANIMATED 2D** mode. Its breathing, blink and speech mouth overlays run in the application; it is separate from the native 3D model. The procedural model is labelled **LIVE 3D** and has a more stylized appearance. Neither is a licensed Sidhu Moose Wala likeness.

No voice recording, cloned voice, downloaded human mesh, animation library or external texture pack is bundled. Speech comes from installed system voices. A supplied licensed SAPI voice can be installed through its vendor and selected by ID. Celebrity character assets have not been supplied; importing and retargeting a future licensed rig requires its actual model, animation/blend-shape definitions and license terms.
