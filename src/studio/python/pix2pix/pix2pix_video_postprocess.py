
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=str, required=True, help="Directory containing input images")
    parser.add_argument("--scale", type=float, default=1.0, help="Scaling factor for the output images")
    args = parser.parse_args()
    scale = args.scale

    # Iterate over all images in the input directory recursively and apply the scaling factor
    import os
    from PIL import Image

    input_dir = args.dir

    num_processed = 0
    for root, _, files in os.walk(input_dir):
        for filename in files:
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                path = os.path.join(root, filename)

            with Image.open(path) as img:
                new_size = (int(img.width * scale), int(img.height * scale))
                img_resized = img.resize(new_size, Image.LANCZOS)
                img_resized.save(path)
                num_processed += 1
    print(f"Processed {num_processed} images.")

if __name__ == "__main__":
    main()

