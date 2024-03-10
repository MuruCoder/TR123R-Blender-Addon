# v0.5.0

import bpy, bmesh

from struct import unpack
from math import sqrt
from gc import collect
from os import path, mkdir
from subprocess import run

from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, FloatProperty, StringProperty, EnumProperty, CollectionProperty
from bpy.types import Operator, OperatorFileListElement


class ImportTRM(Operator, ImportHelper):
    """Load object from TRM file"""
    bl_idname = "io_tombraider123r.trm_import"
    bl_label = "Import TRM"
    bl_options = {'UNDO'}

    filename_ext = ".TRM"

    filter_glob: StringProperty(
        default="*.TRM",
        options={'HIDDEN'},
        maxlen=255,
    )

    files: CollectionProperty(
        type=OperatorFileListElement,
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    directory: StringProperty(
        subtype='DIR_PATH',
    )

    scale: FloatProperty(
        name="Scale",
        description="Scale vertices",
        default=0.01,
    )

    merge_uv: BoolProperty(
        name="Merge by UVs",
        description="Tries to weld non-manifold edges, resulting in mesh welding along UV seams.\n"
                    "Helps with smooth shading & editing",
        default=True
    )

    armature_type: EnumProperty(
        name="Joint Naming",
        description="Vertex groups & bones naming",
        items=(
            ('AUTO', "AUTO", "Try to pick the best"),
            ('ID', "ID", "Internal joint IDs"),
            ('Lara_Body', "Lara Body", "Lara's body & outfits"),
            ('Lara_Hair', "Lara Hair", "Lara's hair"),
        ),
        default='AUTO',
    )

    use_tex: BoolProperty(
        name="Use Textures",
        description="Convert DDS textures to PNG, import and apply to mesh",
        default=False
    )

    episode_dir: EnumProperty(
        name="Episode",
        description="Specify the episode folder if working with TRMs outside game installation",
        items=(
            ('1', "TR I", ""),
            ('2', "TR II", ""),
            ('3', "TR III", "")
        ),
        default='1',
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, 'scale')
        layout.prop(self, 'merge_uv')
        layout.prop(self, 'armature_type')
        layout.prop(self, 'use_tex')

        if self.use_tex:
            layout.prop(self, 'episode_dir')

    def execute(self, context):
        # PROCESS FILES
        completed = 0
        cancelled = 0
        for f in self.files:
            print("\nIMPORTING:", f.name)

            trm_data = readTRM(path.join(self.directory, f.name))
            if trm_data == False:
                cancelled += 1
                print("CANCELLED!")
                continue

            trm_name = str(f.name).removesuffix(self.filename_ext)
            trm_object = processTRM(trm_data, trm_name, self.scale)

            if self.armature_type != 'ID':
                nameVertexGroups(trm_object, self.armature_type, f.name)

            if self.merge_uv:
                mergeByUV(trm_object.data)

            if self.use_tex:
                processTextures(trm_object, trm_data['textures'], self.directory, self.episode_dir)

            bpy.context.collection.objects.link(trm_object)
            completed += 1
            print("DONE.")
            del trm_data
            collect()

        if cancelled != 0:
            self.report({'ERROR'}, "%d Failed, %d Completed Import(s)!" % (cancelled, completed))
        else:
            self.report({'INFO'}, "%d Completed Import(s)." % completed)

        return {'FINISHED'}


def readTRM(filepath):
    data = {'shaders': [], 'textures': [], 'joints': [], 'indices': [], 'vertices': []}

    f = open(filepath, 'rb')

    # TRM\x02 marker
    if unpack('>I', f.read(4))[0] != 0x54524d02:
        print("ERROR: Not a TRM file!")
        f.close()
        return False

    # SHADERS
    num_shaders = unpack('<I', f.read(4))[0]
    for n in range(num_shaders):
        shader = unpack("<11I", f.read(44))
        data['shaders'].append(shader)

    # TEXTURES
    num_textures = unpack('<I', f.read(4))[0]
    data['textures'] = unpack("<%dH" % num_textures, f.read(num_textures * 2))

    # byte align
    if f.tell() % 4: f.seek(4 - (f.tell()%4), 1)

    # UNKNOWN ANIMATION DATA, SKIP OVER
    num_joints = unpack('<I', f.read(4))[0]
    if num_joints > 0:
        f.seek(num_joints * 48, 1)
        num_unknown2 = unpack('<I', f.read(4))[0]
        f.seek(num_unknown2 * 8, 1)
        num_unknown3 = unpack('<I', f.read(4))[0]
        f.seek(num_unknown3 * 4, 1)
        num_unknown4 = unpack('<H', f.read(2))[0]
        num_unknown5 = unpack('<H', f.read(2))[0]
        f.seek(num_unknown3 * num_unknown4 * 48, 1)

    # INDICES & VERTICES
    num_indices = unpack('<I', f.read(4))[0]
    num_vertices = unpack('<I', f.read(4))[0]

    data['indices'] = unpack("<%dH" % num_indices, f.read(num_indices * 2))

    if f.tell() % 4: f.seek(4 - (f.tell()%4), 1)

    for n in range(num_vertices):
        vertex = unpack("<fff12B", f.read(24))
        data['vertices'].append(vertex)

    f.close()

    print("%d Shaders, %d Textures, %d Indices, %d Vertices" % (num_shaders, num_textures, num_indices, num_vertices))
    if num_joints > 0:
        print("%d Joints, %d Unknown2, %d Unknown3, %d Unknown4" % (num_joints, num_unknown2, num_unknown3, num_unknown4))

    return data


def processTRM(data, name, scale):
    shaders = data['shaders']
    textures = data['textures']
    indices = data['indices']
    vertices = data['vertices']

    # CREATE OBJECT
    mesh = bpy.data.meshes.new(name+'_Mesh')
    verts = []
    edges = []
    faces = []
    for v in vertices:
        verts.append((-v[0] * scale, -v[2] * scale, -v[1] * scale))
    for n in range(0, len(indices), 3):
        faces.append((indices[n], indices[n+2], indices[n+1]))
    mesh.from_pydata(verts, edges, faces, shade_flat=False)
    mesh.update(calc_edges=True, calc_edges_loose=True)
    trm = bpy.data.objects.new(name, mesh)

    # NORMALS & VERTEX GROUPS
    normals = []
    max_group = 0

    for v in vertices:
        nr = normalByte2Float(v[3], v[4], v[5])
        normals.append((-nr[0], -nr[2], -nr[1]))
        max_group = max(v[7], v[8], v[9], max_group)

    mesh.use_auto_smooth = True
    mesh.normals_split_custom_set_from_vertices(normals)
    mesh.calc_normals_split()

    groups = trm.vertex_groups
    for n in range(max_group + 1):
        groups.new(name="Joint%d" % n)

    for n in range(len(vertices)):
        if v[11] > 0:
            groups[v[7]].add([n], v[11] / 255, 'ADD')
        if v[12] > 0:
            groups[v[8]].add([n], v[12] / 255, 'ADD')
        if v[13] > 0:
            groups[v[9]].add([n], v[13] / 255, 'ADD')

    # UV DATA
    mesh.uv_layers.new()
    uvs = mesh.uv_layers.active.data
    lps = mesh.loops
    for p in mesh.polygons:
        for i in p.loop_indices:
            v = lps[i].vertex_index
            uvs[i].uv = (vertices[v][10] / 255, (255 - vertices[v][14]) / 255)

    # MATERIALS
    # possible combinations
    materials = []
    for t in textures:
        for s in shaders:
            if s[6] > 0:
                r = range( int(s[5]/3), int((s[5]+s[6])/3) )
                materials.append({'tex': t, 'shdr': s, 'sub': 'A', 'range': r, 'polys': []})
            if s[8] > 0:
                r = range( int(s[7]/3), int((s[7]+s[8])/3) )
                materials.append({'tex': t, 'shdr': s, 'sub': 'B', 'range': r, 'polys': []})
            if s[10] > 0:
                r = range( int(s[9]/3), int((s[9]+s[10])/3) )
                materials.append({'tex': t, 'shdr': s, 'sub': 'C', 'range': r, 'polys': []})

    # distribute polygons
    polygons = mesh.polygons

    for mat in materials:
        for p in mat['range']:
            tex = textures[vertices[polygons[p].vertices[0]][6] - 1]
            if tex == mat['tex']:
                mat['polys'].append(p)

    # create & assign
    current = 0
    for mat in materials:
        if len(mat['polys']) > 0:
            material = createMaterial(mat['tex'], mat['shdr'], mat['sub'])
            trm.data.materials.append(material)
            for p in mat['polys']:
                polygons[p].material_index = current
            current += 1

    mesh.update(calc_edges=True)
    mesh.validate()

    return trm


def normalByte2Float(x, y, z):
    x -= 127
    y -= 127
    z -= 127
    length = sqrt((x * x) + (y * y) + (z * z))
    return (x / length, y / length, z / length)


def int2rgba(i):
    def linear(c):
        if c < 0: return 0
        elif c < 0.04045: return c/12.92
        else: return ((c+0.055)/1.055)**2.4
    r = (i & 0x000000ff)
    g = (i & 0x0000ff00) >> 8
    b = (i & 0x00ff0000) >> 16
    a = (i & 0xff000000) >> 24
    return tuple([linear(c/0xff) for c in (r,g,b)] + [a/255])


def createMaterial(texture, shader, sub):
    mat = bpy.data.materials.new(name="%d_%d_%s_Mat" % (texture, shader[0], sub))
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    main = nodes.new('ShaderNodeOutputMaterial')

    if 'TRMGroup' in bpy.data.node_groups:
        trmg = bpy.data.node_groups['TRMGroup']
    else:
        trmg = bpy.data.node_groups.new(name="TRMGroup", type='ShaderNodeTree')
        trmg.interface.new_socket(name="Color1", in_out ="INPUT", socket_type="NodeSocketColor")
        trmg.interface.new_socket(name="Color2", in_out ="INPUT", socket_type="NodeSocketColor")
        trmg.interface.new_socket(name="Color3", in_out ="INPUT", socket_type="NodeSocketColor")
        trmg.interface.new_socket(name="Color4", in_out ="INPUT", socket_type="NodeSocketColor")
        trmg.interface.new_socket(name="Texture", in_out ="INPUT", socket_type="NodeSocketColor")
        trmg.interface.new_socket(name="Surface", in_out ="OUTPUT", socket_type="NodeSocketShader")
        inp = trmg.nodes.new('NodeGroupInput')
        inp.location = (-100, 0)
        out = trmg.nodes.new('NodeGroupOutput')
        out.location = (100, 0)
        trmg.links.new(trmg.nodes[1].inputs['Surface'], trmg.nodes[0].outputs['Texture'])

    group = nodes.new('ShaderNodeGroup')
    group.location = (-200, 0)
    group.node_tree = trmg
    texture = nodes.new('ShaderNodeTexImage')
    texture.location = (-500, 0)
    mat.node_tree.links.new(group.inputs['Texture'], texture.outputs['Color'])
    mat.node_tree.links.new(main.inputs['Surface'], group.outputs['Surface'])

    mat.node_tree.nodes['Group'].inputs['Color1'].default_value = int2rgba(shader[1])
    mat.node_tree.nodes['Group'].inputs['Color2'].default_value = int2rgba(shader[2])
    mat.node_tree.nodes['Group'].inputs['Color3'].default_value = int2rgba(shader[3])
    mat.node_tree.nodes['Group'].inputs['Color4'].default_value = int2rgba(shader[4])

    return mat


def nameVertexGroups(trm, armature_type, filename):
    # possible vertex group names, 10 per line for easier counting
    joint_names = [
        "root", "hips", "stomach", "chest", "torso", "neck", "head", "jaw", "jaw_lower", "jaw_upper",
        "hip_L", "thigh_L", "thighB_L", "knee_L", "calf_L", "calfB_L", "ankle_L", "foot_L", "toe_L", "toes_L",
        "hip_R", "thigh_R", "thighB_R", "knee_R", "calf_R", "calfB_R", "ankle_R", "foot_R", "toe_R", "toes_R",
        "shoulder_L", "shoulderB_L", "arm_L", "armB_L", "elbow_L", "elbowB_L", "wrist_L", "hand_L", "thumb_L", "fingers_L",
        "shoulder_R", "shoulderB_R", "arm_R", "armB_R", "elbow_R", "elbowB_R", "wrist_R", "hand_R", "thumb_R", "fingers_R",
        "hair_root", "hair1", "hair2", "hair3", "hair4", "hair5", "hair6", "hair7", "hair8", "hair9",
        # more to be added here
    ]

    # lists to get names by order
    joint_lists = {
        'Lara_Hair': {
            'names': [50, 51, 52, 53, 54, 55],
            'auto': ["_HAIR"]
        },
        'Lara_Body': {
            'names': [1, 11, 14, 17, 21, 24, 27, 4, 42, 44, 47, 32, 34, 37, 6],
            'auto': ["OUTFIT_", "HOLSTER_", "HAND_"]
        },
    }

    # decide which list to use
    def autoPick():
        for k in joint_lists.keys():
            for a in joint_lists[k]['auto']:
                if a in filename:
                    return k
        return 'AUTO'

    current = armature_type
    groups = trm.vertex_groups

    if current == 'AUTO':
        current = autoPick()

    if current == 'AUTO' and len(groups) == 1:
        groups[0].name = joint_names[0]

    if current in joint_lists:
        names = joint_lists[current]['names']
        for n in range(min(len(names), len(groups))):
            groups[n].name = joint_names[names[n]]

    return


# merge edges along UV seams
def mergeByUV(mesh):
    normals = []
    for l in mesh.loops:
        normals.append(l.normal.copy())

    meshB = bmesh.new()
    meshB.from_mesh(mesh)
    verts_to_merge = set()
    for e in meshB.edges:
        if not e.is_manifold:
            e.seam = True
            for v in e.verts:
                verts_to_merge.add(v)
    bmesh.ops.remove_doubles(meshB, verts=list(verts_to_merge), dist=0.0001)

    for e in meshB.edges:
        if not e.is_manifold:
            e.seam = False

    meshB.to_mesh(mesh)
    meshB.free()

    mesh.normals_split_custom_set(normals)
    mesh.update()
    return


def processTextures(trm, textures, directory, episode):
    prefs = bpy.context.preferences.addons[__package__].preferences
    converter_path = prefs.converter_path
    game_path = prefs.game_path
    png_path = prefs.png_path

    converter_path_exists = path.exists(converter_path) and converter_path.endswith('.exe')
    game_path_exists = path.isdir(game_path)
    png_path_exists = path.isdir(png_path)
    trm_episode = path.split(path.abspath(path.join(directory, "..")))[-1]
    if trm_episode not in ['1', '2', '3']:
        trm_episode = episode

    for t in textures:
        print(f"- {t}.PNG")

        png = ''
        check = []

        if png_path_exists:
            check += [path.abspath(f"{png_path}/{i}/{t}.png") for i in range(int(trm_episode), 0, -1)]
        if game_path_exists:
            check += [path.abspath(f"{game_path}/{i}/TEX/PNGs/{t}.png") for i in range(int(trm_episode), 0, -1)]
        else:
            check += [path.abspath(path.join(directory, f"../../{i}/TEX/PNGs/{t}.png")) for i in range(int(trm_episode), 0, -1)]

        for f in check:
            if path.isfile(f):
                png = f
                break

        if not png:
            if not converter_path_exists:
                print("- ERROR: Texture Converter path must be specified in Addon Preferences!")
                continue

            dds = ''
            check = []

            if game_path_exists:
                check += [path.abspath(f"{game_path}/{i}/TEX/{t}.DDS") for i in range(int(trm_episode), 0, -1)]
            else:
                check += [path.abspath(path.join(directory, f"../../{i}/TEX/{t}.DDS")) for i in range(int(trm_episode), 0, -1)]

            for f in check:
                if path.isfile(f):
                    dds = f
                    break

            if not dds:
                print("- ERROR: Source DDS could not be found!")
                continue

            dds_episode = path.normpath(dds).split(path.sep)[-3]

            if png_path_exists:
                folder = path.abspath(f"{png_path}/{dds_episode}")
            elif game_path_exists:
                folder = path.abspath(f"{game_path}/{dds_episode}/TEX/PNGs")
            else:
                folder = path.abspath(path.join(directory, f"../../{dds_episode}/TEX/PNGs"))

            if not path.isdir(folder):
                mkdir(folder)

            result = run([converter_path, dds, '-nologo', '-o', folder, '-ft', 'png'])
            png = path.abspath(path.join(folder, f"{t}.png"))

        if png:
            print(f"- From: {path.normpath(png)}.")
            image = bpy.data.images.load(png)
            for mat in trm.data.materials:
                if mat.name.startswith(f"{t}_"):
                    mat.node_tree.nodes["Image Texture"].image = image

    return


def menu_func_import(self, context):
    self.layout.operator(ImportTRM.bl_idname, text="TRM / Tomb Raider I-III R (.trm)")

def register():
    bpy.utils.register_class(ImportTRM)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(ImportTRM)
