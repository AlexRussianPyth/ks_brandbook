#!/usr/bin/env python3
"""Извлекает векторные ассеты (логотип, знак, графэлементы, узор) из Kanalservice_guide.pdf.

Этапы для каждого ассета:
1. Страница рендерится в растр, фирменные цвета ищутся по пикселям, по ним
   вычисляется область (bbox) объекта.
2. Область переносится на временную страницу (show_pdf_page) и экспортируется
   в SVG вместе со всем контентом страницы (текст — кривыми).
3. clean_svg() удаляет из SVG элементы вне viewBox (парсит path-данные,
   учитывает матрицы трансформации) и фон страницы.

Проверка корректности: рендер результата сравнивается пиксельно с рендером
«сырого» SVG (check(): допуск у элементов — 0%, у ассетов с вырезанным фоном —
до 2% на антиалиасинге краёв).

Зависимости: pip install pymupdf numpy
Запуск: python tools/extract_assets.py
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pymupdf as fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "Kanalservice_guide.pdf")
OUT_SVG = os.path.join(ROOT, "assets", "svg")
DPI = 96  # для поиска bbox; экспорт SVG не зависит от DPI

PAGE_BG = {"logo": "#0041a0", "sign": "#0041a0"}  # фон, который режем из этих SVG
NS_XLINK = "{http://www.w3.org/1999/xlink}href"
SVG_TAG = "{http://www.w3.org/2000/svg}"

os.makedirs(OUT_SVG, exist_ok=True)
doc = fitz.open(PDF)

# ---------------------------------------------------------------- bbox поиск


def page_array(pno):
    pix = doc[pno].get_pixmap(dpi=DPI)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr[:, :, :3], pix.width / doc[pno].rect.width


def color_bbox(mask, scale, region=None):
    """Bbox пикселей mask, ограниченный долями region=(x0,y0,x1,y1) от страницы."""
    m = mask
    if region:
        h, w = m.shape
        x0, y0, x1, y1 = region
        roi = np.zeros_like(m)
        roi[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = True
        m = m & roi
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        raise RuntimeError("цветная область не найдена")
    return fitz.Rect(
        xs.min() / scale, ys.min() / scale,
        (xs.max() + 1) / scale, (ys.max() + 1) / scale,
    )


def orange_mask(arr):
    r, g, b = (arr[:, :, i].astype(int) for i in range(3))
    return (r > 200) & (g > 30) & (g < 130) & (b < 80)


def blue_mask(arr):
    r, g, b = (arr[:, :, i].astype(int) for i in range(3))
    return (b > 120) & (r < 70) & (g > 40) & (g < 190)


def white_mask(arr):
    return (arr[:, :, 0] > 220) & (arr[:, :, 1] > 220) & (arr[:, :, 2] > 220)


def grow(rect, pt, page_rect):
    return fitz.Rect(
        max(page_rect.x0, rect.x0 - pt), max(page_rect.y0, rect.y0 - pt),
        min(page_rect.x1, rect.x1 + pt), min(page_rect.y1, rect.y1 + pt),
    )


# ---------------------------------------------------------------- SVG cleaning

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
TOKEN_RE = re.compile(rf"[MmLlHhVvCcSsQqTtAaZz]|{NUM}")


def path_bbox(d):
    """Оценочный bbox path-данных (контрольные точки кривых включаются)."""
    toks = TOKEN_RE.findall(d)
    i, x, y, sx, sy = 0, 0.0, 0.0, 0.0, 0.0
    minx = miny = float("inf")
    maxx = maxy = float("-inf")

    def pt(px, py):
        nonlocal minx, miny, maxx, maxy
        minx, miny = min(minx, px), min(miny, py)
        maxx, maxy = max(maxx, px), max(maxy, py)

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    start = None
    while i < len(toks):
        cmd = toks[i]
        if not cmd.isalpha():
            # неявный повтор предыдущей команды (всегда координатная)
            cmd = prev
            i -= 0
        i += 1
        rel = cmd.islower()
        c = cmd.upper()
        if c == "Z":
            x, y = sx, sy
            prev = cmd
            continue
        if c in ("M", "L", "T"):
            first = True
            while i < len(toks) and not toks[i].isalpha():
                nx, ny = num(), num()
                if rel:
                    nx, ny = x + nx, y + ny
                x, y = nx, ny
                if c == "M" and first:
                    sx, sy = x, y
                    first = False
                pt(x, y)
        elif c == "H":
            while i < len(toks) and not toks[i].isalpha():
                nx = num()
                x = x + nx if rel else nx
                pt(x, y)
        elif c == "V":
            while i < len(toks) and not toks[i].isalpha():
                ny = num()
                y = y + ny if rel else ny
                pt(x, y)
        elif c in ("C",):
            while i < len(toks) and not toks[i].isalpha():
                x1, y1, x2, y2, nx, ny = num(), num(), num(), num(), num(), num()
                if rel:
                    x1, y1, x2, y2, nx, ny = x+x1, y+y1, x+x2, y+y2, x+nx, y+ny
                pt(x1, y1); pt(x2, y2); x, y = nx, ny; pt(x, y)
        elif c in ("S", "Q"):
            while i < len(toks) and not toks[i].isalpha():
                x1, y1, nx, ny = num(), num(), num(), num()
                if rel:
                    x1, y1, nx, ny = x+x1, y+y1, x+nx, y+ny
                pt(x1, y1); x, y = nx, ny; pt(x, y)
        elif c == "A":
            while i < len(toks) and not toks[i].isalpha():
                rx, ry, rot, laf, sf, nx, ny = num(), num(), num(), num(), num(), num(), num()
                if rel:
                    nx, ny = x+nx, y+ny
                pt(nx, ny); pt(nx + 2*rx, ny + 2*ry); pt(nx - 2*rx, ny - 2*ry)
                x, y = nx, ny
        prev = cmd
    if minx == float("inf"):
        return None
    return (minx, miny, maxx, maxy)


def mat_mul(a, b):
    return (
        a[0]*b[0] + a[2]*b[1], a[1]*b[0] + a[3]*b[1],
        a[0]*b[2] + a[2]*b[3], a[1]*b[2] + a[3]*b[3],
        a[0]*b[4] + a[2]*b[5] + a[4], a[1]*b[4] + a[3]*b[5] + a[5],
    )


def parse_transform(s):
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(matrix|translate|scale)\(([^)]*)\)", s or ""):
        v = [float(x) for x in re.findall(NUM, args)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        else:
            continue
        m = mat_mul(m, t)
    return m


def bbox_through(m, bb):
    x0, y0, x1, y1 = bb
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    tx = [m[0]*px + m[2]*py + m[4] for px, py in pts]
    ty = [m[1]*px + m[3]*py + m[5] for px, py in pts]
    return min(tx), min(ty), max(tx), max(ty)


def clean_svg(svg_text, bg_fill=None, margin=1.0):
    """Удаляет элементы вне viewBox и фон страницы; неиспользуемые defs."""
    tree = ET.fromstring(svg_text)
    vb = [float(v) for v in tree.get("viewBox", "0 0 0 0").split()]
    canvas = (vb[0] - margin, vb[1] - margin, vb[0] + vb[2] + margin, vb[1] + vb[3] + margin)
    canvas_area = vb[2] * vb[3]

    def intersects(bb):
        return bb[0] <= canvas[2] and bb[2] >= canvas[0] and bb[1] <= canvas[3] and bb[3] >= canvas[1]

    defs = {}
    for el in tree.iter(SVG_TAG + "path"):
        pid = el.get("id")
        if pid and el.get("d"):
            defs[pid] = path_bbox(el.get("d"))

    def walk(parent, mat):
        for el in list(parent):
            tag = el.tag
            if tag == SVG_TAG + "defs":
                continue
            if not tag.startswith(SVG_TAG):
                parent.remove(el)
                continue
            name = tag[len(SVG_TAG):]
            m = mat_mul(mat, parse_transform(el.get("transform")))
            bb = None
            if name == "path" and el.get("d"):
                bb = path_bbox(el.get("d"))
            elif name == "use":
                href = el.get(NS_XLINK) or el.get("href") or ""
                bb = defs.get(href.lstrip("#"))
                if bb:
                    bb = bbox_through(
                        mat_mul(m, (1, 0, 0, 1, float(el.get("x", 0) or 0), float(el.get("y", 0) or 0))), bb)
            if bb is not None:
                gbb = bbox_through(m, bb)
                fill = (el.get("fill") or "").lower()
                is_bg = (
                    bg_fill and fill == bg_fill
                    and (gbb[2]-gbb[0]) * (gbb[3]-gbb[1]) >= 0.9 * canvas_area
                )
                if not intersects(gbb) or is_bg:
                    parent.remove(el)
                    continue
            if name in ("g", "svg"):
                walk(el, m)
                if not list(el):
                    parent.remove(el)

    walk(tree, (1, 0, 0, 1, 0, 0))

    # убрать неиспользуемые defs
    used = set()
    for el in tree.iter():
        href = el.get(NS_XLINK) or el.get("href")
        if href and href.startswith("#"):
            used.add(href[1:])
    for df in tree.findall(SVG_TAG + "defs"):
        for el in list(df):
            if el.get("id") and el.get("id") not in used:
                df.remove(el)
        if not list(df):
            tree.remove(df)
    # служебные атрибуты
    for attr in ("version",):
        tree.attrib.pop(attr, None)
    return ET.tostring(tree, encoding="unicode")


# ---------------------------------------------------------------- экспорт


def raw_svg(pno, clip):
    """SVG фрагмента страницы (с полным контентом страницы внутри)."""
    tmp = fitz.open()
    page = tmp.new_page(width=clip.width, height=clip.height)
    page.show_pdf_page(fitz.Rect(0, 0, clip.width, clip.height), doc, pno, clip=clip)
    return page.get_svg_image(text_as_path=True)


def export(pno, clip, name, kind=None):
    clip = fitz.Rect(clip)
    raw = raw_svg(pno, clip)
    cleaned = clean_svg(raw, bg_fill=PAGE_BG.get(kind))
    path = os.path.join(OUT_SVG, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + cleaned)
    print(f"{os.path.relpath(path, ROOT)}  {clip.width:.0f}x{clip.height:.0f}pt  "
          f"{len(raw)//1024}KB -> {len(cleaned)//1024}KB")
    return raw, path


def render_png(svg_path, out_path, zoom=2.0):
    d = fitz.open(svg_path)
    d[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True).save(out_path)


def check(raw, svg_path, name, bg_rgb=None):
    """Пиксельное сравнение рендера результата с рендером сырого SVG.

    bg_rgb — цвет, на который сплющивается альфа (фон исходной страницы),
    нужен для ассетов с вырезанным фоном (логотип/знак на синем).
    """
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rp, np_ = os.path.join(td, "r.png"), os.path.join(td, "n.png")
        with open(os.path.join(td, "r.svg"), "w") as f:
            f.write(raw)
        render_png(os.path.join(td, "r.svg"), rp)
        render_png(svg_path, np_)

        def load(p):
            px = fitz.Pixmap(p)
            a = np.frombuffer(px.samples, np.uint8).reshape(px.height, px.width, px.n).astype(float)
            if px.n == 4 and bg_rgb:
                alpha = a[:, :, 3:4] / 255.0
                a = a[:, :, :3] * alpha + np.array(bg_rgb) * (1 - alpha)
                return a
            return a[:, :, :3] if px.n > 3 else a

        aa, bb = load(rp), load(np_)
        if aa.shape != bb.shape:
            return f"{name}: РАЗМЕР {aa.shape} != {bb.shape}"
        diff = np.abs(aa - bb)
        bad = (diff.max(axis=2) > 24).mean()
        # ассеты с вырезанным фоном дают <1% расхождений на антиалиасинге краёв
        threshold = 0.02 if bg_rgb else 0.001
        status = "OK " if bad < threshold else "ПЛОХО"
        return f"{status} {name}: расходящихся пикселей {bad*100:.3f}%"


# ---------------------------------------------------------------- ассеты


def main():
    raws = {}

    # с.21: логотип (плашка + словесный знак) и вариант с дескриптором
    arr, sc = page_array(20)
    plate = color_bbox(orange_mask(arr), sc, region=(0.2, 0.25, 0.8, 0.75))
    desc = color_bbox(
        white_mask(arr), sc,
        region=(plate.x0 / 1920 - 0.08, (plate.y1 + 4) / 1080,
                plate.x1 / 1920 + 0.08, (plate.y1 + 80) / 1080),
    )
    M = 6
    raws["logo-plate.svg"] = export(20, grow(plate, M, doc[20].rect), "logo-plate.svg", kind="logo")
    raws["logo-with-descriptor.svg"] = export(20, grow(plate | desc, M, doc[20].rect),
                                              "logo-with-descriptor.svg", kind="logo")

    # с.23: знак «КС»
    arr, sc = page_array(22)
    sign = color_bbox(orange_mask(arr), sc, region=(0.25, 0.2, 0.75, 0.8))
    raws["sign.svg"] = export(22, grow(sign, 8, doc[22].rect), "sign.svg", kind="sign")

    # с.27: графические элементы (сетка 3 колонки x 2 строки, белый фон)
    arr, sc = page_array(26)
    cells = {
        "element-plate.svg": ((0.30, 0.28, 0.53, 0.55), blue_mask(arr)),    # Плашка
        "element-oval.svg": ((0.53, 0.25, 0.72, 0.55), orange_mask(arr)),   # Овал
        "element-sparkle.svg": ((0.72, 0.28, 0.92, 0.55), blue_mask(arr)),   # Блик
        "element-stream.svg": ((0.30, 0.65, 0.72, 1.00), blue_mask(arr)),    # Ручеек
        "element-shield.svg": ((0.72, 0.65, 0.92, 1.00), orange_mask(arr)),  # Щит
    }
    for name, (region, mask) in cells.items():
        bbox = color_bbox(mask, sc, region=region)
        raws[name] = export(26, grow(bbox, 4, doc[26].rect), name)

    # с.28: узор
    arr, sc = page_array(27)
    pattern = color_bbox(blue_mask(arr), sc, region=(0.3, 0.1, 0.98, 0.95))
    raws["pattern-waves.svg"] = export(27, pattern, "pattern-waves.svg")

    print("--- проверка ---")
    ok = True
    for name, (raw, path) in raws.items():
        bg = (0, 65, 160) if name.startswith(("logo", "sign")) else None
        res = check(raw, path, name, bg_rgb=bg)
        print(res)
        ok = ok and res.startswith("OK")
    if not ok:
        sys.exit(1)
    print("готово")


if __name__ == "__main__":
    main()
