from dataclasses import dataclass, astuple
import struct


@dataclass
class dskmheader_t:
    id: str
    file_type: int  # uint
    filesize: int  # uint
    num_bones: int
    num_meshes: int
    ofs_meshes: int

    def __iter__(self):
        return iter(astuple(self))


@dataclass
class dskmmesh_t:
    shadername: str  # 64 bytes
    meshname: str  # 64 bytes
    num_verts: int  # all uint
    num_tris: int
    num_references: int
    ofs_verts: int
    ofs_texcoords: int
    ofs_indices: int
    ofs_references: int


def get_meshes(all_mesh_bytes:bytes, header: dskmheader_t):
    for i in range(header.num_meshes):
        shadername = all_mesh_bytes[156*i:156*i+64].decode("ascii").rstrip("\x00")
        meshname = all_mesh_bytes[156*i+64:156*i+128].decode("ascii").rstrip("\x00")
        yield dskmmesh_t(shadername, meshname, *struct.unpack("<IIIIIII", all_mesh_bytes[156*i+128:156*i+156]))


def load_skm(path: str):
    with open(path, "rb") as f:  # bsps are binary files
        byte_list = f.read()  # stores all bytes in bytes1 variable (named like that to not interfere with builtin names
    header = dskmheader_t(byte_list[:4].decode("ascii"), *struct.unpack("<IIIII", byte_list[4:24]))
    meshes = list(get_meshes(byte_list[header.ofs_meshes:header.ofs_meshes+header.num_meshes*156], header))

    return header, meshes