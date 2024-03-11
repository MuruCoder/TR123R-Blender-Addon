# v0.5.1

import bpy, bmesh

from struct import pack
from math import sqrt
from gc import collect

from bpy_extras.io_utils import ExportHelper
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy.types import Operator


class ExportTRM(Operator, ExportHelper):
    """Save object as TRM file"""
    bl_idname = "io_tombraider123r.trm_export"
    bl_label = "Export TRM"

    filename_ext = ".TRM"

    filter_glob: StringProperty(
        default="*.TRM",
        options={'HIDDEN'},
        maxlen=255,
    )

    act_only: BoolProperty(
        name="Active Only",
        description="Export only last selected object",
        default=False
    )

    scale: FloatProperty(
        name="Scale",
        description="Scale vertices",
        default=100.0,
    )

    apply_transforms: BoolProperty(
        name="Apply Object Matrix",
        description="Apply object location, rotation and scale",
        default=True,
    )

    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply object modifiers",
        default=False,
    )

    def execute(self, context):
        print("\nEXPORTING...")

        trm_data = {'shaders': {}, 'textures': [], 'indices': [], 'vertices': []}
        objects = []

        # SELECT ACTIVE OBJECT(s) & PROCESS
        if self.act_only:
            obj = bpy.context.active_object
            if obj and obj.type == 'MESH':
                objects.append(obj)
        else:
            for obj in bpy.context.selected_objects:
                if obj.type == 'MESH':
                    objects.append(obj)

        if len(objects) > 0:
            for obj in objects:
                print("- %s -" % obj.name)
                trm_mesh = obj.data.copy()
                if self.apply_modifiers:
                    applyModifiers(trm_mesh, obj)
                triangulateMesh(trm_mesh)
                if self.apply_transforms:
                    processTRM(trm_mesh, trm_data, self.scale, obj.matrix_world)
                else:
                    processTRM(trm_mesh, trm_data, self.scale, False)
                bpy.data.meshes.remove(trm_mesh)
                del trm_mesh
                collect()
        else:
            if self.act_only:
                trm_data['CANCELLED'] = "Active object must be a 3D Object!"
            else:
                trm_data['CANCELLED'] = "Select one or more 3D Objects!"

        if 'CANCELLED' in trm_data:
            print("ERROR: "+trm_data['CANCELLED']+"\nCANCELLED!")
            self.report({'ERROR'}, trm_data['CANCELLED'])
            return {'CANCELLED'}
        else:
            writeTRM(trm_data, self.filepath)
            print("%d Shaders, %d Textures, %d Indices, %d Vertices" % (len(trm_data['shaders']), len(trm_data['textures']), len(trm_data['indices']), len(trm_data['vertices'])))
            print("DONE!")
            self.report({'INFO'}, "Export Completed.")

        return {'FINISHED'}


def processTRM(mesh, data, scale, matrix):
    shaders = data['shaders']
    textures = data['textures']
    vertices = data['vertices']

    # SHADERS & TEXTURES from MATERIALS
    # material_map will be used to refer to shader & texture arrays from polygon.material_index
    # map marks go [0: 'shaderKey', 1: 'subKey', 2: textures_array_id]
    material_map = []

    for mat in mesh.materials:
        mark = ['0_0_0_0_0', 'indicesA', 0]
        # expected material name "[textureID]_[shaderTYPE]_[A,B or C]_Mat"
        ids = mat.name.split("_")
        tex = 8000
        shd = 0
        if ids[0].isnumeric():
            tex = int(ids[0])
        if len(ids)>1 and ids[1].isnumeric():
            shd = int(ids[1])
        if len(ids)>2:
            if ids[2] == 'B': mark[1] = 'indicesB'
            if ids[2] == 'C': mark[1] = 'indicesC'

        if tex in textures:
            mark[2] = textures.index(tex)
        else:
            mark[2] = len(textures)
            textures.append(tex)

        if 'Group' in mat.node_tree.nodes.keys():
            shd1 = rgba2int(mat.node_tree.nodes['Group'].inputs['Color1'].default_value)
            shd2 = rgba2int(mat.node_tree.nodes['Group'].inputs['Color2'].default_value)
            shd3 = rgba2int(mat.node_tree.nodes['Group'].inputs['Color3'].default_value)
            shd4 = rgba2int(mat.node_tree.nodes['Group'].inputs['Color4'].default_value)
        else:
            shd1 = 0
            shd2 = 0
            shd3 = 0
            shd4 = 0
        skey = "%d_%d_%d_%d_%d" % (shd, shd1, shd2, shd3, shd4)
        if skey not in shaders:
            shaders[skey] = {'pack': pack("<5I", shd, shd1, shd2, shd3, shd4), 'indicesA': [], 'indicesB': [], 'indicesC': []}
        mark[0] = skey
        material_map.append(mark)

    # PREPARE INDICES & VERTICES DATA
    num_vertices = len(vertices)
    uvs = mesh.uv_layers.active
    v_order = [0, 2, 1]

    for p in mesh.polygons:
        mark = material_map[p.material_index]
        for i in v_order:
            loop = mesh.loops[p.loop_indices[i]]
            groups = mesh.vertices[loop.vertex_index].groups
            if len(groups) > 3:
                data['CANCELLED'] = "Maximum 3 Joints Allowed per Vertex!"
                return
            uv = uvs.data[p.loop_indices[i]].uv
            if uv[0] < 0 or uv[0] > 1.0 or uv[1] < 0 or uv[1] > 1.0:
                data['CANCELLED'] = "UV Out of Bounds!"
                return
            coords = mesh.vertices[loop.vertex_index].co
            if matrix:
                coords = matrix @ coords
            vertex = packVertex(
                scale,
                coords,
                loop.normal,
                mark[2],
                groups,
                uv
            )
            indices = shaders[mark[0]][mark[1]]
            if vertex in vertices:
                indices.append(vertices.index(vertex))
            else:
                indices.append(num_vertices)
                vertices.append(vertex)
                num_vertices += 1


def writeTRM(data, filepath):
    f = open(filepath, 'wb')

    # TRM\x02 marker
    f.write(pack(">I", 0x54524d02))

    shaders = data['shaders']
    textures = data['textures']
    indices = data['indices']
    vertices = data['vertices']

    # SHADERS
    f.write(pack("<I", len(shaders)))
    for s in shaders:
        shd = shaders[s]
        f.write(shd['pack'])
        f.write(pack("<2I", len(indices), len(shd['indicesA'])))
        indices.extend(shd['indicesA'])
        f.write(pack("<2I", len(indices), len(shd['indicesB'])))
        indices.extend(shd['indicesB'])
        f.write(pack("<2I", len(indices), len(shd['indicesC'])))
        indices.extend(shd['indicesC'])

    # TEXTURES
    f.write(pack("<I", len(textures)))
    for t in textures:
        f.write(pack("<H", t))

    # byte align
    while f.tell() % 4: f.write(b"\x00")

    # JOINTS (CURRENTLY UNKNOWN)
    f.write(pack("<I", 0))

    # INDICES & VERTICES
    f.write(pack("<2I", len(indices), len(vertices)))

    f.write(pack("<%dH" % len(indices), *indices))

    while f.tell() % 4: f.write(b"\x00")

    for v in vertices:
        f.write(v)

    f.close()


def applyModifiers(mesh, obj):
    copy = obj.copy()
    copy.data = mesh
    bpy.context.view_layer.layer_collection.collection.objects.link(copy)
    bpy.context.view_layer.objects.active = copy
    for m in copy.modifiers:
        if m.show_viewport:
            bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(copy, do_unlink=True)
    del copy


def triangulateMesh(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.calc_normals_split()
    mesh.update()


def normalFloat2Byte(x, y, z):
    length = sqrt((x * x) + (y * y) + (z * z))
    if length != 0:
        x = (x / length) * 126
        y = (y / length) * 126
        z = (z / length) * 126
        return (round(x + 127), round(y + 127), round(z + 127))
    return (127, 127, 127)


def rgba2int(rgba):
    r = round(rgba[0] * 255)
    g = round(rgba[1] * 255) << 8
    b = round(rgba[2] * 255) << 16
    a = round(rgba[3] * 255) << 24
    return (r + g + b + a)


def packVertex(scale, coordinate, normal, texture, groups, uv):
    vx = -coordinate.x * scale
    vy = -coordinate.z * scale
    vz = -coordinate.y * scale
    nr = normalFloat2Byte(-normal[0], -normal[1], -normal[2])
    nx = nr[0]
    ny = nr[2]
    nz = nr[1]
    tex = texture + 1
    tu = round(uv[0] * 255)
    tv = 255 - round(uv[1] * 255)
    g1 = 0
    w1 = 255
    g2 = 0
    w2 = 0
    g3 = 0
    w3 = 0
    if len(groups) > 0:
        g1 = groups[0].group
        w1 = round(groups[0].weight * 255)
    if len(groups) > 1:
        g2 = groups[1].group
        w2 = round(groups[1].weight * 255)
    if len(groups) > 2:
        g3 = groups[2].group
        w3 = round(groups[2].weight * 255)
    return pack("<fff12B", vx,vy,vz, nx,ny,nz, tex, g1,g2,g3, tu, w1,w2,w3, tv)


def menu_func_export(self, context):
    self.layout.operator(ExportTRM.bl_idname, text="TRM / Tomb Raider I-III R (.trm)")

def register():
    bpy.utils.register_class(ExportTRM)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(ExportTRM)
