"""Icon Douyin Downloader v2: render 1024 (chong rang cua) -> xuat ico/png."""
from PIL import Image, ImageDraw

BG = (16, 16, 16, 255)
ACCENT = (46, 117, 182, 255)
WHITE = (255, 255, 255, 255)

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([16, 16, S - 16, S - 16], radius=230, fill=BG)

# dau not nhac (ellipse xoay 20 do)
head = Image.new("RGBA", (420, 300), (0, 0, 0, 0))
ImageDraw.Draw(head).ellipse([20, 20, 400, 280], fill=WHITE)
head = head.rotate(20, expand=True, resample=Image.BICUBIC)
img.alpha_composite(head, (150, 560))

# than not
d.rectangle([596, 200, 692, 640], fill=WHITE)
# moc not (tam giac cong tu dinh than)
d.polygon([(596, 200), (880, 260), (860, 380), (700, 340), (692, 420),
           (800, 460), (780, 560), (596, 480)], fill=WHITE)

# huy hieu tai: vong dem tach + tron xanh + mui ten day
cx, cy, r = 748, 752, 208
d.ellipse([cx - r - 28, cy - r - 28, cx + r + 28, cy + r + 28], fill=(0, 0, 0, 0))
d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BG, width=30)
d.line([cx, cy - 110, cx, cy + 60], fill=WHITE, width=58)
d.line([cx - 82, cy - 12, cx, cy + 70], fill=WHITE, width=58)
d.line([cx + 82, cy - 12, cx, cy + 70], fill=WHITE, width=58)
d.line([cx - 96, cy + 118, cx + 96, cy + 118], fill=WHITE, width=48)

img.save("assets/icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save("assets/icon.png")
print("icon v2 OK")
