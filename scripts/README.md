# reel-captions-outro.sh

Burns captions onto a vertical reel and appends the outro lifted from a
reference reel, normalising resolution, frame rate and audio so the two clips
join without stretching or drifting out of sync.

## Requirements

```bash
brew install ffmpeg
pip install mlx-whisper      # fastest on Apple Silicon
# or: pip install openai-whisper
```

Whisper is only needed when the script has to transcribe. Pass `--srt FILE`
to use captions you already have and no transcriber is required.

## Usage

```bash
./reel-captions-outro.sh MAIN_VIDEO SAMPLE_VIDEO [options]
```

`MAIN_VIDEO` is the reel to caption; `SAMPLE_VIDEO` is the reference reel the
outro is taken from. Run with `--help` for the full option list.

## What it does

1. Transcribes the main reel's audio to an `.srt` (skipped with `--srt`).
2. Burns the captions in — bold white, black outline, centred, sitting 18% of
   the frame height up from the bottom, clear of the platform UI.
3. Finds the outro in the sample by detecting the last hard scene cut in its
   closing 20 seconds. Override with `--outro-seconds N` or `--outro-start T`.
4. Scales and pads that segment to the main reel's exact dimensions, frame rate
   and audio format. A differently-shaped outro is letterboxed, never stretched
   or cropped.
5. Concatenates the two and writes an H.264 / AAC MP4 with `+faststart`.

The generated `.srt` is saved next to the output. Speech-to-text gets names and
jargon wrong, so read it, fix any wording, then re-run with `--srt` to reburn.

## Notes

- Caption geometry is expressed in real pixels. The script converts the SRT to
  ASS and rewrites `PlayResX`/`PlayResY` to the video's true size first —
  without that, ffmpeg's hardcoded 384x288 play resolution scales font size and
  margins by roughly 6.7x and pushes the text off-frame.
- `--font` must name a font installed on the machine. libass silently
  substitutes when it cannot find one, so check the first output frame.
- Everything is re-encoded once at `--crf 18` (visually lossless). Lower it for
  more quality, raise it for a smaller file.
