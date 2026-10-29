import tensorflow as tf

import os
import pathlib
import time
import datetime
import argparse
import json
import random

from matplotlib import pyplot as plt



def load(video_set):

  target_frame_path = video_set[0]
  target_frame = tf.io.read_file(target_frame_path)
  target_frame = tf.io.decode_png(target_frame)
  target_frame = tf.cast(target_frame, tf.float32)

  # The second element gets encoded into the alpha channel and the reference image into RGB
  path = video_set[1]
  face_frame = tf.io.read_file(path)
  face_frame = tf.io.decode_png(face_frame, channels=3)
  face_frame = tf.cast(face_frame, tf.float32)
  reference_image_path = video_set[2]
  reference_image = tf.io.read_file(reference_image_path)
  reference_image = tf.io.decode_png(reference_image, channels=3)
  reference_image = tf.cast(reference_image, tf.float32)
  source_frame = tf.concat([face_frame, reference_image[:, :, :1]], axis=-1)
  #source_frame = face_frame

  return source_frame, target_frame

# The batch size of 1 produced better results for the U-Net in the original pix2pix experiment
BATCH_SIZE = 1
# Each image is 640x640 in size
IMG_WIDTH = 640
IMG_HEIGHT = 640
IMG_SCALE = 1.0

OUTPUT_CHANNELS = 3
LAMBDA = 100

def resize(input_image, real_image, height, width):
  input_image = tf.image.resize(input_image, [height, width],
                                method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
  real_image = tf.image.resize(real_image, [height, width],
                               method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)

  return input_image, real_image


def random_crop(input_image, real_image):
  in_ch, real_ch = 4, 3   # input has 4 channels, target has 3
  combined = tf.concat([input_image, real_image], axis=-1)       # [w, h, 7]
  combined = tf.image.random_crop(combined, size=[IMG_HEIGHT, IMG_WIDTH, in_ch + real_ch])
  input_image, real_image = combined[..., :in_ch], combined[..., in_ch:]
  return input_image, real_image

# Normalizing the images to [-1, 1]
def normalize(input_image, real_image):
  input_image = (input_image / 127.5) - 1
  real_image = (real_image / 127.5) - 1

  return input_image, real_image


@tf.function()
def random_jitter(input_image, real_image):
  # Resizing to 670x670
  input_image, real_image = resize(
    input_image,
    real_image,
    IMG_HEIGHT + 30,
    IMG_WIDTH + 30)

  # Random cropping back to 640x640
  input_image, real_image = random_crop(input_image, real_image)

  if tf.random.uniform(()) > 0.5:
    # Random mirroring
    input_image = tf.image.flip_left_right(input_image)
    real_image = tf.image.flip_left_right(real_image)

  return input_image, real_image


def load_image_train(video_pair):
  input_image, real_image = load(video_pair)
  input_image, real_image = random_jitter(input_image, real_image)
  input_image, real_image = normalize(input_image, real_image)

  return input_image, real_image


def load_image_test(video_pair):
  input_image, real_image = load(video_pair)
  input_image, real_image = resize(input_image, real_image,
                                   IMG_HEIGHT, IMG_WIDTH)
  input_image, real_image = normalize(input_image, real_image)

  return input_image, real_image

def downsample(filters, size, apply_batchnorm=True):
  initializer = tf.random_normal_initializer(0., 0.02)

  result = tf.keras.Sequential()
  result.add(
      tf.keras.layers.Conv2D(filters, size, strides=2, padding='same',
                             kernel_initializer=initializer, use_bias=False))

  if apply_batchnorm:
    result.add(tf.keras.layers.BatchNormalization())

  result.add(tf.keras.layers.LeakyReLU())

  return result

def upsample(filters, size, apply_dropout=False):
  initializer = tf.random_normal_initializer(0., 0.02)

  result = tf.keras.Sequential()
  result.add(
    tf.keras.layers.Conv2DTranspose(filters, size, strides=2,
                                    padding='same',
                                    kernel_initializer=initializer,
                                    use_bias=False))

  result.add(tf.keras.layers.BatchNormalization())

  if apply_dropout:
      result.add(tf.keras.layers.Dropout(0.5))

  result.add(tf.keras.layers.ReLU())

  return result

def Generator():
  inputs = tf.keras.layers.Input(shape=[IMG_HEIGHT, IMG_WIDTH, 4])

  down_stack = []
  if IMG_HEIGHT >= 640:
    down_stack.append(downsample(IMG_HEIGHT//4, 4, apply_batchnorm=False))  # (batch_size, 320, 320, 160)
  
  down_stack = down_stack + [
    downsample(IMG_HEIGHT//2, 4, apply_batchnorm=IMG_HEIGHT<640),  # (batch_size, 160, 160, 320)
    downsample(IMG_HEIGHT, 4),  # (batch_size, 80, 80, 640)
    downsample(IMG_HEIGHT*2, 4),  # (batch_size, 40, 40, 1280)
    downsample(IMG_HEIGHT*2, 4),  # (batch_size, 20, 20, 1280)
    downsample(IMG_HEIGHT*2, 4),  # (batch_size, 10, 10, 1280)
    downsample(IMG_HEIGHT*2, 4),  # (batch_size, 5, 5, 1280)
  ]

  up_stack = [
    upsample(IMG_HEIGHT*2, 4, apply_dropout=True),  # (batch_size, 10, 10, 1280)
    upsample(IMG_HEIGHT*2, 4, apply_dropout=True),  # (batch_size, 20, 20, 1280)
    upsample(IMG_HEIGHT*2, 4, apply_dropout=True),  # (batch_size, 40, 40, 1280)
    upsample(IMG_HEIGHT, 4),  # (batch_size, 80, 80, 1280)
    upsample(IMG_HEIGHT//2, 4),  # (batch_size, 160, 160, 640)
  ]
  if IMG_HEIGHT >= 640:
    up_stack.append(upsample(IMG_HEIGHT//4, 4))  # (batch_size, 320, 320, 320)

  initializer = tf.random_normal_initializer(0., 0.02)
  last = tf.keras.layers.Conv2DTranspose(OUTPUT_CHANNELS, 4,
                                         strides=2,
                                         padding='same',
                                         kernel_initializer=initializer,
                                         activation='tanh')  # (batch_size, 640, 640, 3)

  x = inputs

  # Downsampling through the model
  skips = []
  for down in down_stack:
    x = down(x)
    skips.append(x)

  skips = reversed(skips[:-1])

  # Upsampling and establishing the skip connections
  for up, skip in zip(up_stack, skips):
    x = up(x)
    x = tf.keras.layers.Concatenate()([x, skip])

  x = last(x)

  return tf.keras.Model(inputs=inputs, outputs=x)

def generator_loss(disc_generated_output, gen_output, target):
  gan_loss = loss_object(tf.ones_like(disc_generated_output), disc_generated_output)

  # Mean absolute error
  l1_loss = tf.reduce_mean(tf.abs(target - gen_output))

  total_gen_loss = gan_loss + (LAMBDA * l1_loss)

  return total_gen_loss, gan_loss, l1_loss

def Discriminator():
  initializer = tf.random_normal_initializer(0., 0.02)

  inp = tf.keras.layers.Input(shape=[IMG_HEIGHT, IMG_WIDTH, 4], name='input_image')
  tar = tf.keras.layers.Input(shape=[IMG_HEIGHT, IMG_WIDTH, 3], name='target_image')

  x = tf.keras.layers.concatenate([inp, tar])  # (batch_size, 640, 640, channels*2)

  down1 = downsample(IMG_HEIGHT//8, 4, False)(x)  # (batch_size, 320, 320, 80)
  down2 = downsample(IMG_HEIGHT//4, 4)(down1)  # (batch_size, 160, 160, 160)
  down3 = downsample(IMG_HEIGHT//2, 4)(down2)  # (batch_size, 80, 80, 320)

  zero_pad1 = tf.keras.layers.ZeroPadding2D()(down3)  # (batch_size, 82, 82, 320)
  conv = tf.keras.layers.Conv2D(IMG_HEIGHT, 4, strides=1,
                                kernel_initializer=initializer,
                                use_bias=False)(zero_pad1)  # (batch_size, 79, 79, 640)

  batchnorm1 = tf.keras.layers.BatchNormalization()(conv)

  leaky_relu = tf.keras.layers.LeakyReLU()(batchnorm1)

  zero_pad2 = tf.keras.layers.ZeroPadding2D()(leaky_relu)  # (batch_size, 81, 81, 512)

  last = tf.keras.layers.Conv2D(1, 4, strides=1,
                                kernel_initializer=initializer)(zero_pad2)  # (batch_size, 78, 78, 1)

  return tf.keras.Model(inputs=[inp, tar], outputs=last)

def discriminator_loss(disc_real_output, disc_generated_output):
  real_loss = loss_object(tf.ones_like(disc_real_output), disc_real_output)

  generated_loss = loss_object(tf.zeros_like(disc_generated_output), disc_generated_output)

  total_disc_loss = real_loss + generated_loss

  return total_disc_loss

@tf.function
def train_step(input_image, target, step):
  with tf.GradientTape() as gen_tape, tf.GradientTape() as disc_tape:
    gen_output = generator(input_image, training=True)

    disc_real_output = discriminator([input_image, target], training=True)
    disc_generated_output = discriminator([input_image, gen_output], training=True)

    gen_total_loss, gen_gan_loss, gen_l1_loss = generator_loss(disc_generated_output, gen_output, target)
    disc_loss = discriminator_loss(disc_real_output, disc_generated_output)

  generator_gradients = gen_tape.gradient(gen_total_loss,
                                          generator.trainable_variables)
  discriminator_gradients = disc_tape.gradient(disc_loss,
                                               discriminator.trainable_variables)

  generator_optimizer.apply_gradients(zip(generator_gradients,
                                          generator.trainable_variables))
  discriminator_optimizer.apply_gradients(zip(discriminator_gradients,
                                              discriminator.trainable_variables))

  with summary_writer.as_default():
    tf.summary.scalar('gen_total_loss', gen_total_loss, step=step//1000)
    tf.summary.scalar('gen_gan_loss', gen_gan_loss, step=step//1000)
    tf.summary.scalar('gen_l1_loss', gen_l1_loss, step=step//1000)
    tf.summary.scalar('disc_loss', disc_loss, step=step//1000)

def fit(train_ds, steps):
  start = time.time()

  for step, (input_image, target) in train_ds.repeat().take(steps).enumerate():
    if (step) % 1000 == 0:

      if step != 0:
        print(f'Time taken for 1000 steps: {time.time()-start:.2f} sec\n')

      start = time.time()

      print(f"Step: {step//1000}k")

    train_step(input_image, target, step)

    # Training step
    if (step+1) % 10 == 0:
      print('.', end='', flush=True)


    # Save (checkpoint) the model every 1k steps
    if (step + 1) % 1000 == 0:
      checkpoint_manager.save()

def generate_images(model, test_input, tar):
    start = time.time()
    prediction = model(test_input, training=False)
    elapsed = time.time() - start
    print(f"Time taken for inference: {elapsed:.2f} sec")
    plt.figure(figsize=(15, 15))

    # Split the test input into face (alpha channel) and reference image (RGB)
    face = test_input[0, :, :, 3:]
    reference_image = test_input[0, :, :, :3]

    display_list = [face, reference_image, tar[0], prediction[0]]
    title = ['Face (Alpha Channel)', 'Reference Image', 'Ground Truth', 'Predicted Image']

    for i in range(4):
        plt.subplot(1, 4, i+1)
        plt.title(title[i])
        plt.imshow(display_list[i] * 0.5 + 0.5)
        plt.axis('off')
    plt.savefig(f"inference/output_{time.time()}.png")

def generate_video(test_dataset, generator, video_path):
    import cv2
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = None

    # Generate a video from the test dataset using the generator model
    num_frames = 500
    num_fps = 16
    for input, _ in test_dataset.take(num_frames):
        prediction = generator(input, training=False)
        frame = (prediction[0].numpy() * 0.5 + 0.5) * 255
        frame = frame.astype('uint8')
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if out is None:
            height, width, _ = frame.shape
            out = cv2.VideoWriter(video_path, fourcc, num_fps, (width, height))
        out.write(frame)
    if out is not None:
        out.release()

def skip(iterator, count):
    try:
      for _ in range(count):
        next(iterator)
    except StopIteration:
        pass

def run_inference(test_dataset, generator, video_path=None):
    if not os.path.exists("inference"):
        os.makedirs("inference")

    if video_path is not None:
      generate_video(test_dataset, generator, video_path)
    else:
      iterator = iter(test_dataset)
      for _ in range(5):
        inp, tar = next(iterator)
        generate_images(generator, inp, tar)
        skip(iterator, 40)

def export_model(generator):
  # Keras 3 (TF >= 2.16):
  generator.export(args.export_path)

def load_dataset(dataset_path):
  training_dir = PATH / "train"
  testing_dir = PATH / "test"

  # The dataset is split into train and test directories - containing 2 images: face and source image per pair
  training_videos = []
  testing_videos = []
  fps = 16
  for video_dir in training_dir.iterdir():
    if video_dir.is_dir():
      files = sorted(video_dir.glob("*.png"))
      for i in range(len(files) // 2):
        training_videos.append((str(files[i*2]), str(files[i*2+1]), str(files[0])))

  for video_dir in testing_dir.iterdir():
    if video_dir.is_dir():
      files = sorted(video_dir.glob("*.png"))
      for i in range(len(files) // 2):
        testing_videos.append((str(files[i*2]), str(files[i*2+1]), str(files[0])))

  # training_videos is a list of (str, str) tuples (convert with str() as before)
  train_paths = tf.constant(training_videos)   # shape [N, 3], dtype string
  test_paths  = tf.constant(testing_videos)

  train_dataset = (
      tf.data.Dataset.from_tensor_slices(train_paths)
      .shuffle(len(training_videos))           # shuffle cheap path strings, before decoding
      .map(load_image_train, num_parallel_calls=tf.data.AUTOTUNE)
      .batch(BATCH_SIZE)
      .prefetch(tf.data.AUTOTUNE)
  )

  test_dataset = (
      tf.data.Dataset.from_tensor_slices(test_paths)
      .map(load_image_test, num_parallel_calls=tf.data.AUTOTUNE)
      .batch(BATCH_SIZE)
  )
  return train_dataset, test_dataset

parser = argparse.ArgumentParser()
parser.add_argument('--memory_limit', type=int, default=8192, help='Memory limit for GPU in MB')
parser.add_argument("--dev", action='store_true', help="Flag to indicate development mode")
subparsers = parser.add_subparsers(help="Sub-commands for training, inference, and export")

# Sub-parser for export command
export_parser = subparsers.add_parser("export", help="Export the model to ONNX format")
export_parser.add_argument('--export-path', type=str, required=True, help='Path to save the exported ONNX model')

# Sub-parser for training command
train_parser = subparsers.add_parser("train", help="Train the model")
train_parser.add_argument("--num-steps", type=int, default=20000, help="Number of steps for training")
train_parser.add_argument('--dataset_path', dest='train_dataset_path', type=str, required=True, help='Path to the dataset')

# Sub-parser for inference command
inference_parser = subparsers.add_parser("inference", help="Run inference with the model")
inference_parser.add_argument('--video', action='store', type=str, help='Whether inference should produce a video output and the path to save it if enabled')
inference_parser.add_argument('--dataset_path', dest='inference_dataset_path', type=str, required=True, help='Path to the dataset')

args = parser.parse_args()
training = hasattr(args, 'train_dataset_path') and args.num_steps is not None
inference = hasattr(args, 'inference_dataset_path') and args.video is not None
export = hasattr(args, 'export_path') and args.export_path is not None
dev = args.dev
dataset_path = None
if training:
  dataset_path = args.train_dataset_path
elif inference:
  dataset_path = args.inference_dataset_path


if training and (args.num_steps < 1 or args.num_steps % 1000 != 0):
    raise ValueError("Number of steps must be a positive multiple of 1000.")

#In Dev mode the images are scaled down for faster processing (half resolution)
if dev:
  IMG_SCALE = 0.5
  IMG_HEIGHT = int(IMG_HEIGHT * IMG_SCALE)
  IMG_WIDTH = int(IMG_WIDTH * IMG_SCALE)

tf.config.experimental.set_virtual_device_configuration(
  tf.config.experimental.list_physical_devices('GPU')[0],
  [tf.config.experimental.VirtualDeviceConfiguration(memory_limit=args.memory_limit)]
)

if training or inference:
  PATH = pathlib.Path(dataset_path)
  train_dataset, test_dataset = load_dataset(dataset_path)

generator = Generator()
loss_object = tf.keras.losses.BinaryCrossentropy(from_logits=True)
discriminator = Discriminator()

generator_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)
discriminator_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)

checkpoint_dir = './training_checkpoints_video'
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt")
checkpoint = tf.train.Checkpoint(generator_optimizer=generator_optimizer,
                                 discriminator_optimizer=discriminator_optimizer,
                                 generator=generator,
                                 discriminator=discriminator)
checkpoint_manager = tf.train.CheckpointManager(checkpoint, checkpoint_dir, max_to_keep=3,
                                               checkpoint_name="ckpt")

# Restoring the latest checkpoint in checkpoint_dir
latest_ckpt = checkpoint_manager.latest_checkpoint
if latest_ckpt:
    checkpoint.restore(latest_ckpt)
    print(f"Restored from {latest_ckpt}")
else:
    print("No checkpoint found.")

if __name__ == "__main__":
    if training:
        log_dir="logs/"
        summary_writer = tf.summary.create_file_writer(
        log_dir + "fit/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        fit(train_dataset, steps=args.num_steps)
    elif inference:
      if args.video:
        # Run the trained model on a few examples from the test set and produce a video output
        run_inference(test_dataset, generator, video_path=args.video)
      else:
        # Run the trained model on a few examples from the test set
        run_inference(test_dataset, generator)
    elif export:
        export_model(generator)


