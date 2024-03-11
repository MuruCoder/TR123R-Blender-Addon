bl_info = {
    "name": "TRM Format (Tomb Raider I-III Remastered)",
    "description": "Import/Export addon for .TRM files.",
    "version": (0, 5, 1),
    "blender": (4, 0, 0),
    "author": "MuruCoder, MaRaider, Czarpos @ www.tombraiderforums.com",
    "location": "File > Import-Export",
    "category": "Import-Export",
    "warning": "Blender doesn't natively support this game's DDS format.",
    "doc_url": "https://www.tombraiderforums.com/showthread.php?t=228896",
    "tracker_url": "https://www.tombraiderforums.com/showthread.php?t=228896"
}


if "bpy" in locals():
    from importlib import reload
    if "trm_import" in locals():
        reload(trm_import)
    if "trm_export" in locals():
        reload(trm_export)
    del reload


import bpy, os
from . import trm_import, trm_export
from bpy.types import AddonPreferences, UILayout
from bpy.props import StringProperty


def absolutePath(key):
    prefs = bpy.context.preferences.addons[__package__].preferences
    if key in prefs and prefs[key].startswith('//'):
        prefs[key] = os.path.abspath(bpy.path.abspath(prefs[key]))


class PT_TRM_Preferences(AddonPreferences):
    bl_idname = __package__

    converter_path: StringProperty(
        name="Texture Converter",
        description='Path to "texconv.exe" file.\n'
                    'No conversion if a target PNG already exists',
        subtype='FILE_PATH',
        update=lambda s, c: absolutePath('converter_path'),
        default="texconv.exe"
    )

    game_path: StringProperty(
        name="Game Path",
        description='"Tomb Raider I-III Remastered" installation directory.\n'
                    'Used to find & convert textures via the converter.\n'
                    'Leave empty to look for folders relative to the TRMs being handled',
        subtype='DIR_PATH',
        update=lambda s, c: absolutePath('game_path'),
        default=""
    )

    png_path: StringProperty(
        name="Converted PNGs",
        description='Custom directory to save PNGs converted from DDS files.\n'
                    'Leave empty to use "TEX/PNGs" folders in game directory',
        subtype='DIR_PATH',
        update=lambda s, c: absolutePath('png_path'),
        default=""
    )

    def draw(self, context):
        layout = UILayout(self.layout)
        col = layout.column()

        col.prop(self, 'converter_path')
        col.prop(self, 'game_path')
        col.prop(self, 'png_path')

        col.separator()
        row = col.row()
        row.label(text='Download "texconv.exe" converter from:')
        op = row.operator('wm.url_open', text="Microsoft's GitHub Releases")
        op.url = "https://github.com/microsoft/DirectXTex/wiki/Texconv"


def register():
    bpy.utils.register_class(PT_TRM_Preferences)
    trm_import.register()
    trm_export.register()

def unregister():
    trm_export.unregister()
    trm_import.unregister()
    bpy.utils.unregister_class(PT_TRM_Preferences)

if __name__ == "__main__":
    register()
