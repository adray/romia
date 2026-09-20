import torch, glob, numpy as np
import argparse
import os
from transformers import CLIPVisionModelWithProjection, CLIPImageProcessor
from PIL import Image

def load_embeddings(path):
    data = np.load(path, allow_pickle=True).item()  # dict: {frame_path: vector}
    return data

parser = argparse.ArgumentParser(
    description="Generate embeddings from videos."
)
parser.add_argument("input", type=str, help="Path to the videos")
parser.add_argument("-o", "--output", type=str, default="embeddings.npy",
                        help="Where to write results (default: overwrite the input file)")
args = parser.parse_args()


model = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-large-patch14")
proc = CLIPImageProcessor.from_pretrained("openai/clip-vit-large-patch14")
model.eval()

embeds = {}
if os.path.exists(args.output):
    embeds = load_embeddings(args.output)

sourcePath = f"{args.input}/**/*.png"
print(sourcePath)
written = 0
for path in glob.glob(sourcePath):
    if path in embeds:
        continue
    print(path)
    img = Image.open(path).convert("RGB")
    inputs = proc(images=img, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs).image_embeds  # shape (1, 768)
    embeds[path] = out.squeeze().numpy()
    written += 1

if written > 0:
    np.save(args.output, embeds)
    print(f"Saved embeddings. {written} new embeddings")
else:
    print("Skipped no new embeddings")
