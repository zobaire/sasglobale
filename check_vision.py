"""One-off: describe the imported image with Gemini vision."""
import sys, os, base64, io, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brain.config import load_dotenv
env = load_dotenv()
key = env.get("GEMINI_API_KEY", "").strip()

from openai import OpenAI
from PIL import Image

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imports", "deb55930-835d-4f7e-9cb4-3ab787b9e2b0.jpg")
img = Image.open(path); img.load(); img = img.convert("RGB")
w, h = img.size
scale = min(1.0, 1024 / max(w, h))
if scale < 1.0:
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
buf = io.BytesIO(); img.save(buf, format="JPEG", quality=80)
b64 = base64.b64encode(buf.getvalue()).decode("ascii")
print(f"payload {len(b64)//1024} KB")

client = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=key, timeout=90.0)
t0 = time.time()
resp = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role":"user","content":[
        {"type":"text","text":"Describe this image in detail. What do you see?"},
        {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
    ]}],
    temperature=0.2,
)
print(f"({time.time()-t0:.1f}s)")
print(resp.choices[0].message.content)
