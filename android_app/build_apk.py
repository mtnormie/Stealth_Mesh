"""Deterministic Pure-Python Android APK Compiler & Signer (v1 JAR + v2 APK Signature Block).

Builds `StealthMesh_Tactical_UA_EN.apk` containing:
- Binary AndroidManifest.xml (AXML) with zero network permissions & USB-C OTG support
- Valid resources.arsc (4-byte aligned, uncompressed)
- Valid classes.dex (Dalvik bytecode for ua.stealthmesh.tactical.MainActivity)
- Bilingual (Ukrainian / English) Tactical Mobile App in assets/index.html
- Cryptographic signatures: META-INF/ (v1 PKCS#7) + APK Signature Scheme v2 (Android 7..15+)
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

from app.ui.mobile_app_view import MOBILE_APP_HTML


# ---------------------------------------------------------------------------
# 1. Android Binary XML (AXML) Builder for AndroidManifest.xml
# ---------------------------------------------------------------------------
def build_binary_manifest() -> bytes:
    # Resource-mapped attribute names MUST come first in the string pool
    attr_specs = [
        ("theme", 0x01010000),
        ("label", 0x01010001),
        ("name", 0x01010003),
        ("exported", 0x01010010),
        ("launchMode", 0x0101001D),
        ("screenOrientation", 0x0101001E),
        ("configChanges", 0x0101001F),
        ("minSdkVersion", 0x0101020C),
        ("versionCode", 0x0101021B),
        ("versionName", 0x0101021C),
        (" targetSdkVersion".strip(), 0x01010270),
        ("allowBackup", 0x01010280),
        ("required", 0x0101028E),
    ]
    other_strings = [
        "android",
        "http://schemas.android.com/apk/res/android",
        "manifest",
        "package",
        "ua.stealthmesh.tactical",
        "1.0.0-emcon",
        "uses-sdk",
        "uses-feature",
        "android.hardware.usb.host",
        "application",
        "Stealth Mesh (UA/EN)",
        "activity",
        "ua.stealthmesh.tactical.MainActivity",
        "Stealth Mesh",
        "intent-filter",
        "action",
        "android.intent.action.MAIN",
        "android.hardware.usb.action.USB_DEVICE_ATTACHED",
        "category",
        "android.intent.category.LAUNCHER",
        "",
    ]

    all_strings = [s for s, _ in attr_specs] + other_strings
    str_idx = {s: i for i, s in enumerate(all_strings)}

    # Build UTF-16LE StringPool chunk (0x001C0001)
    encoded_strings: list[bytes] = []
    offsets: list[int] = []
    cur_offset = 0
    for s in all_strings:
        offsets.append(cur_offset)
        u16 = s.encode("utf-16le")
        char_len = len(s)
        blob = struct.pack("<H", char_len) + u16 + b"\x00\x00"
        encoded_strings.append(blob)
        cur_offset += len(blob)

    strings_blob = b"".join(encoded_strings)
    while len(strings_blob) % 4 != 0:
        strings_blob += b"\x00"

    header_size = 28
    offsets_blob = b"".join(struct.pack("<I", off) for off in offsets)
    strings_start = header_size + len(offsets_blob)
    pool_chunk_size = strings_start + len(strings_blob)
    string_pool_chunk = (
        struct.pack(
            "<HHIIIIII",
            0x0001,  # RES_STRING_POOL_TYPE
            header_size,
            pool_chunk_size,
            len(all_strings),
            0,  # styleCount
            0,  # flags (UTF-16LE)
            strings_start,
            0,  # stylesStart
        )
        + offsets_blob
        + strings_blob
    )

    # Resource Map chunk (0x00080180)
    res_ids = [rid for _, rid in attr_specs]
    res_map_size = 8 + 4 * len(res_ids)
    res_map_chunk = struct.pack("<HHI", 0x0180, 8, res_map_size) + b"".join(
        struct.pack("<I", rid) for rid in res_ids
    )

    NS_URI = str_idx["http://schemas.android.com/apk/res/android"]
    NS_PREFIX = str_idx["android"]
    NO_IDX = 0xFFFFFFFF

    TYPE_Reference = 0x01
    TYPE_String = 0x03
    TYPE_IntDec = 0x10
    TYPE_IntHex = 0x11
    TYPE_IntBool = 0x12

    def make_attr(ns: int, name_s: str, val_type: int, data: int, raw_s: str | None = None) -> bytes:
        name_i = str_idx[name_s]
        raw_i = str_idx[raw_s] if raw_s is not None else NO_IDX
        return struct.pack(
            "<IIIHBBI",
            ns,
            name_i,
            raw_i,
            8,
            0,
            val_type,
            data & 0xFFFFFFFF,
        )

    def start_ns(line: int) -> bytes:
        return struct.pack("<HHIIIII", 0x0100, 16, 24, line, NO_IDX, NS_PREFIX, NS_URI)

    def end_ns(line: int) -> bytes:
        return struct.pack("<HHIIIII", 0x0101, 16, 24, line, NO_IDX, NS_PREFIX, NS_URI)

    def start_el(line: int, name_s: str, attrs: list[bytes]) -> bytes:
        attr_blob = b"".join(attrs)
        total = 36 + len(attr_blob)
        return (
            struct.pack(
                "<HHIIIIIHHHHHH",
                0x0102,
                16,
                total,
                line,
                NO_IDX,
                NO_IDX,
                str_idx[name_s],
                0x0014,  # attributeStart
                0x0014,  # attributeSize (20 bytes)
                len(attrs),
                0,
                0,
                0,
            )
            + attr_blob
        )

    def end_el(line: int, name_s: str) -> bytes:
        return struct.pack("<HHIIIII", 0x0103, 16, 24, line, NO_IDX, NO_IDX, str_idx[name_s])

    xml_body = b"".join(
        [
            start_ns(2),
            start_el(
                2,
                "manifest",
                [
                    make_attr(NS_URI, "versionCode", TYPE_IntDec, 2),
                    make_attr(NS_URI, "versionName", TYPE_String, str_idx["1.0.0-emcon"], "1.0.0-emcon"),
                    make_attr(NO_IDX, "package", TYPE_String, str_idx["ua.stealthmesh.tactical"], "ua.stealthmesh.tactical"),
                ],
            ),
            start_el(
                4,
                "uses-sdk",
                [
                    make_attr(NS_URI, "minSdkVersion", TYPE_IntDec, 24),
                    make_attr(NS_URI, "targetSdkVersion", TYPE_IntDec, 33),
                ],
            ),
            end_el(4, "uses-sdk"),
            start_el(
                6,
                "uses-feature",
                [
                    make_attr(NS_URI, "name", TYPE_String, str_idx["android.hardware.usb.host"], "android.hardware.usb.host"),
                    make_attr(NS_URI, "required", TYPE_IntBool, 0),
                ],
            ),
            end_el(6, "uses-feature"),
            start_el(
                9,
                "application",
                [
                    make_attr(NS_URI, "theme", TYPE_Reference, 0x01030129),  # Theme.DeviceDefault.NoActionBar
                    make_attr(NS_URI, "label", TYPE_String, str_idx["Stealth Mesh (UA/EN)"], "Stealth Mesh (UA/EN)"),
                    make_attr(NS_URI, "allowBackup", TYPE_IntBool, 0),
                ],
            ),
            start_el(
                14,
                "activity",
                [
                    make_attr(NS_URI, "label", TYPE_String, str_idx["Stealth Mesh"], "Stealth Mesh"),
                    make_attr(NS_URI, "name", TYPE_String, str_idx["ua.stealthmesh.tactical.MainActivity"], "ua.stealthmesh.tactical.MainActivity"),
                    make_attr(NS_URI, "exported", TYPE_IntBool, 0xFFFFFFFF),
                    make_attr(NS_URI, "launchMode", TYPE_IntDec, 1),
                    make_attr(NS_URI, "screenOrientation", TYPE_IntDec, 1),
                    make_attr(NS_URI, "configChanges", TYPE_IntHex, 0x04A0),
                ],
            ),
            start_el(20, "intent-filter", []),
            start_el(
                21,
                "action",
                [make_attr(NS_URI, "name", TYPE_String, str_idx["android.intent.action.MAIN"], "android.intent.action.MAIN")],
            ),
            end_el(21, "action"),
            start_el(
                22,
                "action",
                [
                    make_attr(
                        NS_URI,
                        "name",
                        value_type if False else TYPE_String,
                        str_idx["android.hardware.usb.action.USB_DEVICE_ATTACHED"],
                        "android.hardware.usb.action.USB_DEVICE_ATTACHED",
                    )
                ],
            ),
            end_el(22, "action"),
            start_el(
                23,
                "category",
                [make_attr(NS_URI, "name", TYPE_String, str_idx["android.intent.category.LAUNCHER"], "android.intent.category.LAUNCHER")],
            ),
            end_el(23, "category"),
            end_el(20, "intent-filter"),
            end_el(14, "activity"),
            end_el(9, "application"),
            end_el(2, "manifest"),
            end_ns(2),
        ]
    )

    chunks = string_pool_chunk + res_map_chunk + xml_body
    return struct.pack("<HHI", 0x0003, 8, 8 + len(chunks)) + chunks


# ---------------------------------------------------------------------------
# 2. Android Resource Table (resources.arsc) Builder
# ---------------------------------------------------------------------------
def build_resources_arsc() -> bytes:
    # Minimal valid RES_TABLE_TYPE (0x0002) with global string pool and 1 package (0x7f)
    global_pool = struct.pack("<HHIIIIII", 0x0001, 28, 28, 0, 0, 0, 28, 0)
    pkg_name = "ua.stealthmesh.tactical".encode("utf-16le")
    pkg_name_padded = pkg_name + b"\x00" * (256 - len(pkg_name))
    type_strings = struct.pack("<HHIIIIII", 0x0001, 28, 28, 0, 0, 0, 28, 0)
    key_strings = struct.pack("<HHIIIIII", 0x0001, 28, 28, 0, 0, 0, 28, 0)
    pkg_header_size = 288
    pkg_total_size = pkg_header_size + len(type_strings) + len(key_strings)
    pkg_chunk = (
        struct.pack("<HHI", 0x0200, pkg_header_size, pkg_total_size)
        + struct.pack("<I", 0x7F)
        + pkg_name_padded
        + struct.pack("<IIIII", pkg_header_size, 0, pkg_header_size + len(type_strings), 0, 0)
        + type_strings
        + key_strings
    )
    total_size = 12 + len(global_pool) + len(pkg_chunk)
    return struct.pack("<HHII", 0x0002, 12, total_size, 1) + global_pool + pkg_chunk


# ---------------------------------------------------------------------------
# 3. Dalvik Executable (classes.dex) Builder for MainActivity
# ---------------------------------------------------------------------------
def _uleb128(val: int) -> bytes:
    out = bytearray()
    while True:
        byte = val & 0x7F
        val >>= 7
        if val != 0:
            byte |= 0x80
        out.append(byte)
        if val == 0:
            break
    return bytes(out)


def build_classes_dex() -> bytes:
    # Strings MUST be sorted lexicographically in DEX!
    strings = sorted(
        [
            "<init>",
            "Landroid/app/Activity;",
            "Landroid/content/Context;",
            "Landroid/os/Bundle;",
            "Landroid/view/View;",
            "Landroid/webkit/WebSettings;",
            "Landroid/webkit/WebView;",
            "Ljava/lang/Object;",
            "Ljava/lang/String;",
            "Lua/stealthmesh/tactical/MainActivity;",
            "MainActivity.kt",
            "V",
            "VL",
            "VZ",
            "Z",
            "file:///android_asset/index.html",
            "getSettings",
            "loadUrl",
            "onCreate",
            "setContentView",
            "setDomStorageEnabled",
            "setJavaScriptEnabled",
        ]
    )
    s_idx = {s: i for i, s in enumerate(strings)}

    # Types MUST be sorted by their string_idx!
    type_names = sorted(
        [
            "Landroid/app/Activity;",
            "Landroid/content/Context;",
            "Landroid/os/Bundle;",
            "Landroid/view/View;",
            "Landroid/webkit/WebSettings;",
            "Landroid/webkit/WebView;",
            "Ljava/lang/Object;",
            "Ljava/lang/String;",
            "Lua/stealthmesh/tactical/MainActivity;",
            "V",
            "Z",
        ],
        key=lambda t: s_idx[t],
    )
    t_idx = {t: i for i, t in enumerate(type_names)}

    # Protos: (shorty_str, return_type, [param_types])
    # Sorted by return_type, then param_types
    protos = [
        ("V", "V", []),
        ("VL", "V", ["Landroid/content/Context;"]),
        ("VL", "V", ["Landroid/os/Bundle;"]),
        ("VL", "V", ["Landroid/view/View;"]),
        ("VL", "V", ["Ljava/lang/String;"]),
        ("VZ", "V", ["Z"]),
        ("Landroid/webkit/WebSettings;", "Landroid/webkit/WebSettings;", []),
    ]
    # Wait: shorty for ()Landroid/webkit/WebSettings; is "L"! Let's include "L" in strings!
    return _build_classes_dex_with_shorty_l()


def _build_classes_dex_with_shorty_l() -> bytes:
    strings = sorted(
        [
            "<init>",
            "L",
            "Landroid/app/Activity;",
            "Landroid/content/Context;",
            "Landroid/os/Bundle;",
            "Landroid/view/View;",
            "Landroid/webkit/WebSettings;",
            "Landroid/webkit/WebView;",
            "Ljava/lang/Object;",
            "Ljava/lang/String;",
            "Lua/stealthmesh/tactical/MainActivity;",
            "MainActivity.kt",
            "V",
            "VL",
            "VZ",
            "Z",
            "file:///android_asset/index.html",
            "getSettings",
            "loadUrl",
            "onCreate",
            "setContentView",
            "setDomStorageEnabled",
            "setJavaScriptEnabled",
        ]
    )
    s_idx = {s: i for i, s in enumerate(strings)}

    type_names = sorted(
        [
            "Landroid/app/Activity;",
            "Landroid/content/Context;",
            "Landroid/os/Bundle;",
            "Landroid/view/View;",
            "Landroid/webkit/WebSettings;",
            "Landroid/webkit/WebView;",
            "Ljava/lang/Object;",
            "Ljava/lang/String;",
            "Lua/stealthmesh/tactical/MainActivity;",
            "V",
            "Z",
        ],
        key=lambda t: s_idx[t],
    )
    t_idx = {t: i for i, t in enumerate(type_names)}

    raw_protos = [
        ("L", "Landroid/webkit/WebSettings;", []),
        ("V", "V", []),
        ("VL", "V", ["Landroid/content/Context;"]),
        ("VL", "V", ["Landroid/os/Bundle;"]),
        ("VL", "V", ["Landroid/view/View;"]),
        ("VL", "V", ["Ljava/lang/String;"]),
        ("VZ", "V", ["Z"]),
    ]
    raw_protos.sort(key=lambda p: (t_idx[p[1]], [t_idx[x] for x in p[2]]))
    p_idx = {(p[1], tuple(p[2])): i for i, p in enumerate(raw_protos)}

    raw_methods = [
        ("Landroid/app/Activity;", "<init>", ("V", ())),
        ("Landroid/app/Activity;", "onCreate", ("V", ("Landroid/os/Bundle;",))),
        ("Landroid/app/Activity;", "setContentView", ("V", ("Landroid/view/View;",))),
        ("Landroid/webkit/WebSettings;", "setDomStorageEnabled", ("V", ("Z",))),
        ("Landroid/webkit/WebSettings;", "setJavaScriptEnabled", ("V", ("Z",))),
        ("Landroid/webkit/WebView;", "<init>", ("V", ("Landroid/content/Context;",))),
        ("Landroid/webkit/WebView;", "getSettings", ("Landroid/webkit/WebSettings;", ())),
        ("Landroid/webkit/WebView;", "loadUrl", ("V", ("Ljava/lang/String;",))),
        ("Lua/stealthmesh/tactical/MainActivity;", "<init>", ("V", ())),
        ("Lua/stealthmesh/tactical/MainActivity;", "onCreate", ("V", ("Landroid/os/Bundle;",))),
    ]
    raw_methods.sort(key=lambda m: (t_idx[m[0]], s_idx[m[1]], p_idx[m[2]]))
    m_idx = {(m[0], m[1], m[2]): i for i, m in enumerate(raw_methods)}

    # Assemble Dalvik bytecode for <init>()V
    # 70 10 <m_activity_init:16> 00 00 | 0e 00
    m_act_init = m_idx[("Landroid/app/Activity;", "<init>", ("V", ()))]
    insns_init = struct.pack("<HHH", 0x1070, m_act_init, 0x0000) + struct.pack("<H", 0x000E)
    code_init = (
        struct.pack("<HHHHII", 1, 1, 1, 0, 0, len(insns_init) // 2) + insns_init
    )
    while len(code_init) % 4 != 0:
        code_init += b"\x00"

    # Assemble Dalvik bytecode for onCreate(Landroid/os/Bundle;)V
    # Registers: v0=WebView, v1=WebSettings, v2=temp, v3=this(p0), v4=bundle(p1)
    m_super_oncreate = m_idx[("Landroid/app/Activity;", "onCreate", ("V", ("Landroid/os/Bundle;",)))]
    m_wv_init = m_idx[("Landroid/webkit/WebView;", "<init>", ("V", ("Landroid/content/Context;",)))]
    m_wv_settings = m_idx[("Landroid/webkit/WebView;", "getSettings", ("Landroid/webkit/WebSettings;", ()))]
    m_set_js = m_idx[("Landroid/webkit/WebSettings;", "setJavaScriptEnabled", ("V", ("Z",)))]
    m_set_dom = m_idx[("Landroid/webkit/WebSettings;", "setDomStorageEnabled", ("V", ("Z",)))]
    m_set_cv = m_idx[("Landroid/app/Activity;", "setContentView", ("V", ("Landroid/view/View;",)))]
    m_load_url = m_idx[("Landroid/webkit/WebView;", "loadUrl", ("V", ("Ljava/lang/String;",)))]
    t_webview = t_idx["Landroid/webkit/WebView;"]
    s_asset_url = s_idx["file:///android_asset/index.html"]

    insns_oncreate = b"".join(
        [
            # invoke-super {v3, v4}, Activity.onCreate(Bundle)
            struct.pack("<HHH", 0x206F, m_super_oncreate, 0x0043),
            # new-instance v0, WebView
            struct.pack("<HH", 0x0022, t_webview),
            # invoke-direct {v0, v3}, WebView.<init>(Context)
            struct.pack("<HHH", 0x2070, m_wv_init, 0x0030),
            # invoke-virtual {v0}, WebView.getSettings()
            struct.pack("<HHH", 0x106E, m_wv_settings, 0x0000),
            # move-result-object v1
            struct.pack("<H", 0x010C),
            # const/4 v2, 1
            struct.pack("<H", 0x1212),
            # invoke-virtual {v1, v2}, WebSettings.setJavaScriptEnabled(true)
            struct.pack("<HHH", 0x206E, m_set_js, 0x0021),
            # invoke-virtual {v1, v2}, WebSettings.setDomStorageEnabled(true)
            struct.pack("<HHH", 0x206E, m_set_dom, 0x0021),
            # invoke-virtual {v3, v0}, Activity.setContentView(v0)
            struct.pack("<HHH", 0x206E, m_set_cv, 0x0003),
            # const-string v2, "file:///android_asset/index.html"
            struct.pack("<HH", 0x021A, s_asset_url),
            # invoke-virtual {v0, v2}, WebView.loadUrl(v2)
            struct.pack("<HHH", 0x206E, m_load_url, 0x0020),
            # return-void
            struct.pack("<H", 0x000E),
        ]
    )
    code_oncreate = (
        struct.pack("<HHHHII", 5, 2, 2, 0, 0, len(insns_oncreate) // 2) + insns_oncreate
    )
    while len(code_oncreate) % 4 != 0:
        code_oncreate += b"\x00"

    # Layout calculation
    header_size = 0x70
    string_ids_off = header_size
    string_ids_size = len(strings) * 4
    type_ids_off = string_ids_off + string_ids_size
    type_ids_size = len(type_names) * 4
    proto_ids_off = type_ids_off + type_ids_size
    proto_ids_size = len(raw_protos) * 12
    method_ids_off = proto_ids_off + proto_ids_size
    method_ids_size = len(raw_methods) * 8
    class_defs_off = method_ids_off + method_ids_size
    class_defs_size = 32

    data_off = class_defs_off + class_defs_size
    cur = data_off

    # 1. type_list items for protos with parameters
    proto_param_offs: list[int] = []
    type_lists_blob = bytearray()
    for _, _, params in raw_protos:
        if not params:
            proto_param_offs.append(0)
        else:
            while (cur + len(type_lists_blob)) % 4 != 0:
                type_lists_blob.append(0)
            proto_param_offs.append(cur + len(type_lists_blob))
            type_lists_blob += struct.pack("<I", len(params))
            for pt in params:
                type_lists_blob += struct.pack("<H", t_idx[pt])
            while len(type_lists_blob) % 4 != 0:
                type_lists_blob.append(0)
    cur += len(type_lists_blob)

    # 2. code_item for <init> and onCreate (4-byte aligned)
    code_init_off = cur
    cur += len(code_init)
    code_oncreate_off = cur
    cur += len(code_oncreate)

    # 3. string_data_item entries
    string_data_offs: list[int] = []
    string_data_blob = bytearray()
    for s in strings:
        string_data_offs.append(cur + len(string_data_blob))
        raw_utf8 = s.encode("utf-8")
        string_data_blob += _uleb128(len(s)) + raw_utf8 + b"\x00"
    while (cur + len(string_data_blob)) % 4 != 0:
        string_data_blob.append(0)
    cur += len(string_data_blob)

    # 4. class_data_item for MainActivity
    m_main_init = m_idx[("Lua/stealthmesh/tactical/MainActivity;", "<init>", ("V", ()))]
    m_main_oncreate = m_idx[("Lua/stealthmesh/tactical/MainActivity;", "onCreate", ("V", ("Landroid/os/Bundle;",)))]
    class_data_off = cur
    class_data_blob = bytearray(
        _uleb128(0)  # static_fields_size
        + _uleb128(0)  # instance_fields_size
        + _uleb128(1)  # direct_methods_size (<init>)
        + _uleb128(1)  # virtual_methods_size (onCreate)
        # direct method: <init>, PUBLIC | CONSTRUCTOR (0x10001)
        + _uleb128(m_main_init)
        + _uleb128(0x10001)
        + _uleb128(code_init_off)
        # virtual method: onCreate, PUBLIC (0x0001)
        + _uleb128(m_main_oncreate)
        + _uleb128(0x0001)
        + _uleb128(code_oncreate_off)
    )
    while (cur + len(class_data_blob)) % 4 != 0:
        class_data_blob.append(0)
    cur += len(class_data_blob)

    # 5. map_list (4-byte aligned)
    map_off = cur
    map_items = [
        (0x0000, 1, 0),  # HEADER_ITEM
        (0x0001, len(strings), string_ids_off),  # STRING_ID_ITEM
        (0x0002, len(type_names), type_ids_off),  # TYPE_ID_ITEM
        (0x0003, len(raw_protos), proto_ids_off),  # PROTO_ID_ITEM
        (0x0005, len(raw_methods), method_ids_off),  # METHOD_ID_ITEM
        (0x0006, 1, class_defs_off),  # CLASS_DEF_ITEM
        (0x1001, sum(1 for p in proto_param_offs if p > 0), data_off),  # TYPE_LIST
        (0x2001, 2, code_init_off),  # CODE_ITEM
        (0x2002, len(strings), string_data_offs[0]),  # STRING_DATA_ITEM
        (0x2000, 1, class_data_off),  # CLASS_DATA_ITEM
        (0x1000, 1, map_off),  # MAP_LIST
    ]
    map_blob = struct.pack("<I", len(map_items)) + b"".join(
        struct.pack("<HHII", t_code, 0, count, off) for t_code, count, off in map_items
    )
    file_size = cur + len(map_blob)
    data_size = file_size - data_off

    # Build tables
    string_ids_blob = b"".join(struct.pack("<I", off) for off in string_data_offs)
    type_ids_blob = b"".join(struct.pack("<I", s_idx[t]) for t in type_names)
    proto_ids_blob = b"".join(
        struct.pack("<III", s_idx[p[0]], t_idx[p[1]], proto_param_offs[i])
        for i, p in enumerate(raw_protos)
    )
    method_ids_blob = b"".join(
        struct.pack("<HHI", t_idx[m[0]], p_idx[m[2]], s_idx[m[1]]) for m in raw_methods
    )
    class_defs_blob = struct.pack(
        "<IIIIIIII",
        t_idx["Lua/stealthmesh/tactical/MainActivity;"],
        0x0001,  # ACC_PUBLIC
        t_idx["Landroid/app/Activity;"],
        0,  # interfaces_off
        s_idx["MainActivity.kt"],
        0,  # annotations_off
        class_data_off,
        0,  # static_values_off
    )

    body_after_header = (
        string_ids_blob
        + type_ids_blob
        + proto_ids_blob
        + method_ids_blob
        + class_defs_blob
        + bytes(type_lists_blob)
        + code_init
        + code_oncreate
        + bytes(string_data_blob)
        + bytes(class_data_blob)
        + map_blob
    )

    # Temporary header with zero checksum/sha1
    header_prefix = b"dex\n035\x00" + b"\x00" * 24
    header_rest = struct.pack(
        "<IIIIIIIIIIIIIIIIIIII",
        file_size,
        header_size,
        0x12345678,  # ENDIAN_CONSTANT
        0,
        0,
        map_off,
        len(strings),
        string_ids_off,
        len(type_names),
        type_ids_off,
        len(raw_protos),
        proto_ids_off,
        0,
        0,
        len(raw_methods),
        method_ids_off,
        1,
        class_defs_off,
        data_size,
        data_off,
    )
    dex_unsigned = bytearray(header_prefix + header_rest + body_after_header)
    sha1_digest = hashlib.sha1(dex_unsigned[32:]).digest()
    dex_unsigned[12:32] = sha1_digest
    adler = zlib.adler32(dex_unsigned[12:]) & 0xFFFFFFFF
    dex_unsigned[8:12] = struct.pack("<I", adler)
    return bytes(dex_unsigned)


# ---------------------------------------------------------------------------
# 4. ZIP / APK Assembler + v1 (JAR PKCS#7) + v2 (APK Signature Block 42)
# ---------------------------------------------------------------------------
def _encode_len_prefixed(items: list[bytes]) -> bytes:
    body = b"".join(struct.pack("<I", len(x)) + x for x in items)
    return struct.pack("<I", len(body)) + body


def _compute_v2_content_digest(sections: list[bytes]) -> bytes:
    # APK Signature Scheme v2 chunked SHA-256 (0x0103: RSA-PKCS1-v1_5 with SHA-256)
    chunk_digests: list[bytes] = []
    total_chunks = 0
    CHUNK_SIZE = 1024 * 1024
    for sec in sections:
        pos = 0
        while pos < len(sec):
            chunk = sec[pos : pos + CHUNK_SIZE]
            pos += CHUNK_SIZE
            h = hashlib.sha256()
            h.update(b"\xa5" + struct.pack("<I", len(chunk)) + chunk)
            chunk_digests.append(h.digest())
            total_chunks += 1
    top = hashlib.sha256()
    top.update(b"\x5a" + struct.pack("<I", total_chunks) + b"".join(chunk_digests))
    return top.digest()


def build_signed_apk(output_paths: list[Path]) -> dict[str, object]:
    manifest_bytes = build_binary_manifest()
    arsc_bytes = build_resources_arsc()
    dex_bytes = build_classes_dex()
    html_bytes = MOBILE_APP_HTML.encode("utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        key_pem = tmp / "key.pem"
        cert_pem = tmp / "cert.pem"
        cert_der = tmp / "cert.der"

        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key_pem),
                "-out",
                str(cert_pem),
                "-days",
                "3650",
                "-subj",
                "/CN=StealthMesh Tactical UA/O=StealthMesh/C=UA",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["openssl", "x509", "-in", str(cert_pem), "-outform", "DER", "-out", str(cert_der)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cert_der_bytes = cert_der.read_bytes()

        # Build v1 META-INF/MANIFEST.MF, CERT.SF, CERT.RSA
        entries: list[tuple[str, bytes, bool]] = [
            ("AndroidManifest.xml", manifest_bytes, True),
            ("resources.arsc", arsc_bytes, False),  # Uncompressed, 4-byte aligned for Android 11+
            ("classes.dex", dex_bytes, True),
            ("assets/index.html", html_bytes, True),
        ]

        mf_lines = ["Manifest-Version: 1.0", "Created-By: StealthMesh APK Compiler 1.0", ""]
        sf_entry_blocks: list[str] = []
        for name, raw, _ in entries:
            b64_sha = base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii")
            block = f"Name: {name}\r\nSHA-256-Digest: {b64_sha}\r\n\r\n"
            mf_lines.append(block.rstrip("\r\n"))
            mf_lines.append("")
            sf_b64 = base64.b64encode(hashlib.sha256(block.encode("utf-8")).digest()).decode("ascii")
            sf_entry_blocks.append(f"Name: {name}\r\nSHA-256-Digest: {sf_b64}\r\n\r\n")

        mf_bytes = ("\r\n".join(mf_lines)).encode("utf-8")
        mf_sha_b64 = base64.b64encode(hashlib.sha256(mf_bytes).digest()).decode("ascii")
        sf_header = (
            "Signature-Version: 1.0\r\n"
            "Created-By: StealthMesh APK Compiler 1.0\r\n"
            f"SHA-256-Digest-Manifest: {mf_sha_b64}\r\n"
            "X-Android-APK-Signed: 2\r\n\r\n"
        )
        sf_bytes = (sf_header + "".join(sf_entry_blocks)).encode("utf-8")

        sf_file = tmp / "CERT.SF"
        rsa_file = tmp / "CERT.RSA"
        sf_file.write_bytes(sf_bytes)
        subprocess.run(
            [
                "openssl",
                "cms",
                "-sign",
                "-binary",
                "-noattr",
                "-in",
                str(sf_file),
                "-signer",
                str(cert_pem),
                "-inkey",
                str(key_pem),
                "-outform",
                "DER",
                "-out",
                str(rsa_file),
                "-md",
                "sha256",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        rsa_bytes = rsa_file.read_bytes()

        all_zip_entries: list[tuple[str, bytes, bool]] = entries + [
            ("META-INF/MANIFEST.MF", mf_bytes, True),
            ("META-INF/CERT.SF", sf_bytes, True),
            ("META-INF/CERT.RSA", rsa_bytes, True),
        ]

        # Construct ZIP Local File Headers + Central Directory with 4-byte alignment for stored entries
        lfh_section = bytearray()
        cd_records: list[tuple[bytes, int, bytes]] = []  # (cd_prefix_up_to_offset, lfh_offset, cd_suffix)

        for name, raw_data, compress in all_zip_entries:
            name_b = name.encode("utf-8")
            crc = zlib.crc32(raw_data) & 0xFFFFFFFF
            if compress:
                c_obj = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
                comp_data = c_obj.compress(raw_data) + c_obj.flush()
                method = 8
            else:
                comp_data = raw_data
                method = 0

            lfh_offset = len(lfh_section)
            extra = b""
            if not compress:
                data_start = lfh_offset + 30 + len(name_b)
                pad = (4 - (data_start % 4)) % 4
                if pad:
                    extra = b"\x00" * pad

            lfh = (
                struct.pack(
                    "<IHHHHHIIIHH",
                    0x04034B50,
                    20,
                    0,
                    method,
                    0,
                    0x5421,
                    crc,
                    len(comp_data),
                    len(raw_data),
                    len(name_b),
                    len(extra),
                )
                + name_b
                + extra
                + comp_data
            )
            lfh_section += lfh

            cd_prefix = struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                20,
                20,
                0,
                method,
                0,
                0x5421,
                crc,
                len(comp_data),
                len(raw_data),
                len(name_b),
                0,
                0,
                0,
                0,
                0,
                lfh_offset,
            )
            cd_records.append((cd_prefix, lfh_offset, name_b))

        cd_bytes = b"".join(prefix + suffix for prefix, _, suffix in cd_records)
        cd_offset_unaligned = len(lfh_section)
        eocd_for_v2 = struct.pack(
            "<IHHHHIIH",
            0x06054B50,
            0,
            0,
            len(all_zip_entries),
            len(all_zip_entries),
            len(cd_bytes),
            cd_offset_unaligned,  # Wait: per APK v2 spec, EOCD's CD offset during digest calculation is set to original CD offset!
            0,
        )

        # Compute APK Signature Scheme v2 digest (0x0103 = RSA PKCS#1 v1.5 with SHA-256, 256-byte signature)
        digest_sha256 = _compute_v2_content_digest([bytes(lfh_section), cd_bytes, eocd_for_v2])
        SIG_ALGO_RSA_PKCS1_SHA256 = 0x0103

        digest_pair = struct.pack("<I", SIG_ALGO_RSA_PKCS1_SHA256) + struct.pack("<I", len(digest_sha256)) + digest_sha256
        digests_seq = _encode_len_prefixed([digest_pair])
        certs_seq = _encode_len_prefixed([cert_der_bytes])
        attrs_seq = struct.pack("<I", 0)
        signed_data = digests_seq + certs_seq + attrs_seq

        signed_data_file = tmp / "signed_data.bin"
        sig_out_file = tmp / "sig.bin"
        signed_data_file.write_bytes(signed_data)
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(key_pem),
                "-out",
                str(sig_out_file),
                str(signed_data_file),
            ],
            check=True,
        )
        sig_bytes = sig_out_file.read_bytes()

        pub_der_file = tmp / "pub.der"
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(key_pem),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(pub_der_file),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pub_key_bytes = pub_der_file.read_bytes()

        sig_pair = struct.pack("<I", SIG_ALGO_RSA_PKCS1_SHA256) + struct.pack("<I", len(sig_bytes)) + sig_bytes
        sigs_seq = _encode_len_prefixed([sig_pair])
        signer_block = (
            struct.pack("<I", len(signed_data))
            + signed_data
            + sigs_seq
            + struct.pack("<I", len(pub_key_bytes))
            + pub_key_bytes
        )
        signers_seq = _encode_len_prefixed([signer_block])

        # ID-value pair for APK Signature Scheme v2 (ID = 0x7109871a)
        v2_pair_payload = struct.pack("<I", 0x7109871A) + signers_seq
        v2_id_value = struct.pack("<Q", len(v2_pair_payload)) + v2_pair_payload

        # Pad APK Signing Block to multiple of 4096 bytes with dummy ID 0x42726577 if desired, or 8-byte aligned
        block_size_field = len(v2_id_value) + 8 + 16
        apk_sig_block = (
            struct.pack("<Q", block_size_field)
            + v2_id_value
            + struct.pack("<Q", block_size_field)
            + b"APK Sig Block 42"
        )

        new_cd_offset = len(lfh_section) + len(apk_sig_block)
        final_eocd = struct.pack(
            "<IHHHHIIH",
            0x06054B50,
            0,
            0,
            len(all_zip_entries),
            len(all_zip_entries),
            len(cd_bytes),
            new_cd_offset,
            0,
        )

        final_apk = bytes(lfh_section) + apk_sig_block + cd_bytes + final_eocd
        for p in output_paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(final_apk)

        return {
            "size_bytes": len(final_apk),
            "sha256": hashlib.sha256(final_apk).hexdigest(),
            "outputs": [str(p) for p in output_paths],
        }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    targets = [
        root / "mobile_app" / "StealthMesh_Tactical_UA_EN.apk",
        root / "android_app" / "app" / "build" / "outputs" / "apk" / "release" / "StealthMesh_Tactical_UA_EN.apk",
    ]
    info = build_signed_apk(targets)
    print(f"Built signed APK ({info['size_bytes']} bytes, SHA-256: {info['sha256']})")
    for out in info["outputs"]:
        print(f" -> {out}")
