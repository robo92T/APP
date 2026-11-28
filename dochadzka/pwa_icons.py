"""Generate installable PWA PNG icons on demand, without storing employee data."""
from functools import lru_cache
from io import BytesIO

@lru_cache(maxsize=3)
def icon_png(size: int) -> bytes:
    if size not in (180,192,512):
        raise ValueError("Unsupported PWA icon size")
    from PIL import Image, ImageDraw
    scale=3
    d=size*scale
    im=Image.new("RGB",(d,d),"#112747")
    draw=ImageDraw.Draw(im)
    m=int(d*.15)
    draw.rounded_rectangle((m,m,d-m,d-m),radius=int(d*.19),fill="#547aff")
    cx=cy=d//2
    radius=int(d*.22)
    stroke=max(3,int(d*.05))
    draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),
        outline="#ffffff",width=stroke)
    draw.line((cx,cy-int(d*.14),cx,cy+int(d*.01)),fill="#ffffff",width=stroke)
    draw.line((cx,cy,cx+int(d*.12),cy+int(d*.085)),fill="#ffffff",width=stroke)
    dot=int(d*.025)
    draw.ellipse((cx-dot,cy-dot,cx+dot,cy+dot),fill="#ffffff")
    im=im.resize((size,size),Image.Resampling.LANCZOS)
    output=BytesIO();im.save(output,format="PNG",optimize=True)
    return output.getvalue()
