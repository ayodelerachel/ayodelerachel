#!/usr/bin/env bash
#
# reel-captions-outro.sh
#
# Burns captions (CC) onto a reel and appends the outro lifted from a
# reference reel, normalising resolution / fps / audio so the two clips
# concatenate cleanly.
#
#   ./reel-captions-outro.sh MAIN_VIDEO SAMPLE_VIDEO [options]
#
# See --help for the full option list.

set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
log() { printf '\033[1;36m==>\033[0m %s\n' "$*" >&2; }

usage() {
  cat <<'USAGE'
Usage: reel-captions-outro.sh MAIN_VIDEO SAMPLE_VIDEO [options]

  MAIN_VIDEO     the reel to caption (audio is transcribed from this)
  SAMPLE_VIDEO   the reference reel whose outro gets appended

Options:
  -o, --output PATH     output file (default: <main>_captioned_outro.mp4)
      --srt PATH        use an existing .srt instead of transcribing
      --no-captions     skip captions, only append the outro
      --no-outro        skip the outro, only burn captions
      --outro-seconds N take the last N seconds of SAMPLE_VIDEO as the outro
                        (default: auto-detect the final scene cut)
      --outro-start T   take SAMPLE_VIDEO from timestamp T to its end
      --outro-audio MODE  keep|mute  (default: keep)
      --lang CODE       transcription language hint, e.g. en, fr
      --model NAME      whisper model (default: medium)
      --font NAME       caption font (default: Helvetica Neue)
      --font-scale F    caption size as a fraction of video height (default: .045)
      --margin-v PX     caption distance from the bottom edge (default: 18% of height)
      --uppercase       force captions to uppercase
      --crf N           x264 quality, lower is better (default: 18)
      --keep-temp       leave intermediate files in place for inspection
  -h, --help            show this message

Examples:
  ./reel-captions-outro.sh reel3.mp4 "PHLD reel 1.mp4"
  ./reel-captions-outro.sh reel3.mp4 sample.mp4 --outro-seconds 3 --uppercase
  ./reel-captions-outro.sh reel3.mp4 sample.mp4 --srt my-captions.srt -o final.mp4
USAGE
}

# ---------------------------------------------------------------- arguments
MAIN=""; SAMPLE=""; OUTPUT=""
SRT_IN=""; DO_CAPTIONS=1; DO_OUTRO=1
OUTRO_SECONDS=""; OUTRO_START=""; OUTRO_AUDIO="keep"
LANG_HINT=""; MODEL="medium"
FONT="Helvetica Neue"; FONT_SCALE="0.045"; MARGIN_V=""
UPPERCASE=0; CRF=18; KEEP_TEMP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)        usage; exit 0 ;;
    -o|--output)      OUTPUT="${2:?}"; shift 2 ;;
    --srt)            SRT_IN="${2:?}"; shift 2 ;;
    --no-captions)    DO_CAPTIONS=0; shift ;;
    --no-outro)       DO_OUTRO=0; shift ;;
    --outro-seconds)  OUTRO_SECONDS="${2:?}"; shift 2 ;;
    --outro-start)    OUTRO_START="${2:?}"; shift 2 ;;
    --outro-audio)    OUTRO_AUDIO="${2:?}"; shift 2 ;;
    --lang)           LANG_HINT="${2:?}"; shift 2 ;;
    --model)          MODEL="${2:?}"; shift 2 ;;
    --font)           FONT="${2:?}"; shift 2 ;;
    --font-scale)     FONT_SCALE="${2:?}"; shift 2 ;;
    --margin-v)       MARGIN_V="${2:?}"; shift 2 ;;
    --uppercase)      UPPERCASE=1; shift ;;
    --crf)            CRF="${2:?}"; shift 2 ;;
    --keep-temp)      KEEP_TEMP=1; shift ;;
    -*)               die "unknown option: $1" ;;
    *)
      if   [[ -z "$MAIN"   ]]; then MAIN="$1"
      elif [[ -z "$SAMPLE" ]]; then SAMPLE="$1"
      else die "unexpected argument: $1"; fi
      shift ;;
  esac
done

# Paths pasted from Finder often carry stray surrounding whitespace.
MAIN="$(printf '%s' "$MAIN" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
SAMPLE="$(printf '%s' "$SAMPLE" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

[[ -n "$MAIN" ]] || { usage; exit 1; }
[[ -f "$MAIN" ]] || die "main video not found: $MAIN"
if (( DO_OUTRO )); then
  [[ -n "$SAMPLE" ]] || die "a sample video is required unless you pass --no-outro"
  [[ -f "$SAMPLE" ]] || die "sample video not found: $SAMPLE"
fi
[[ "$OUTRO_AUDIO" == keep || "$OUTRO_AUDIO" == mute ]] || die "--outro-audio must be keep or mute"
(( DO_CAPTIONS || DO_OUTRO )) || die "--no-captions and --no-outro together leave nothing to do"
command -v ffmpeg  >/dev/null || die "ffmpeg not found — install it with: brew install ffmpeg"
command -v ffprobe >/dev/null || die "ffprobe not found — install it with: brew install ffmpeg"

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="${MAIN%.*}_captioned_outro.mp4"
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/reel-edit.XXXXXX")"
cleanup() { (( KEEP_TEMP )) && log "temp files kept in $TMP" || rm -rf "$TMP"; }
trap cleanup EXIT

probe() { ffprobe -v error -select_streams "$1" -show_entries "$2" -of default=nw=1:nk=1 "$3" 2>/dev/null | head -1; }

# ------------------------------------------------------- main video geometry
W="$(probe v:0 stream=width "$MAIN")"
H="$(probe v:0 stream=height "$MAIN")"
[[ -n "$W" && -n "$H" ]] || die "could not read video dimensions from $MAIN"

RAW_FPS="$(probe v:0 stream=r_frame_rate "$MAIN")"
FPS="$(awk -F/ '{ if (NF==2 && $2>0) printf "%.4f", $1/$2; else printf "%s", $1 }' <<<"${RAW_FPS:-30}")"
AR="$(probe a:0 stream=sample_rate "$MAIN")"; AR="${AR:-48000}"
ACH="$(probe a:0 stream=channels "$MAIN")"; ACH="${ACH:-2}"
(( ACH > 2 )) && ACH=2
HAS_MAIN_AUDIO=1
[[ -n "$(probe a:0 stream=index "$MAIN")" ]] || HAS_MAIN_AUDIO=0

if (( HAS_MAIN_AUDIO )); then
  log "main: ${W}x${H} @ ${FPS}fps, audio ${AR}Hz/${ACH}ch"
else
  log "main: ${W}x${H} @ ${FPS}fps, no audio track"
fi

# ------------------------------------------------------------ 1. transcribe
SRT=""
if (( DO_CAPTIONS )); then
  if [[ -n "$SRT_IN" ]]; then
    [[ -f "$SRT_IN" ]] || die "subtitle file not found: $SRT_IN"
    SRT="$TMP/captions.srt"
    cp "$SRT_IN" "$SRT"
    log "using supplied captions: $SRT_IN"
  elif (( ! HAS_MAIN_AUDIO )); then
    die "$MAIN has no audio track to transcribe — pass --srt or --no-captions"
  else
    WHISPER=""
    for candidate in mlx_whisper whisper; do
      command -v "$candidate" >/dev/null && { WHISPER="$candidate"; break; }
    done
    [[ -n "$WHISPER" ]] || die "no transcriber found. Install one of:
  pip install mlx-whisper      # fastest on Apple Silicon
  pip install openai-whisper   # portable
…or generate captions elsewhere and pass them with --srt FILE"

    log "transcribing with $WHISPER (model: $MODEL) — this takes a few minutes"
    WARGS=(--model "$MODEL" --output_format srt --output_dir "$TMP")
    [[ -n "$LANG_HINT" ]] && WARGS+=(--language "$LANG_HINT")
    # Short caption lines read far better on a vertical reel. These flags are
    # only present on newer builds, so fall back silently when unsupported.
    if "$WHISPER" --help 2>&1 | grep -q -- --max_line_width; then
      WARGS+=(--word_timestamps True --max_line_width 24 --max_line_count 2)
    fi
    "$WHISPER" "$MAIN" "${WARGS[@]}" >/dev/null

    SRT="$(find "$TMP" -maxdepth 1 -name '*.srt' -print -quit)"
    [[ -n "$SRT" ]] || die "transcription produced no .srt file"
  fi

  if (( UPPERCASE )); then
    # Uppercase the dialogue only; indices and timecodes stay untouched.
    awk '/^[0-9]+$/ || /-->/ || NF==0 { print; next } { print toupper($0) }' \
      "$SRT" > "$TMP/upper.srt"
    SRT="$TMP/upper.srt"
  fi

  CUES="$(grep -c -- '-->' "$SRT" || true)"
  log "captions ready: ${CUES:-0} cues"
fi

# --------------------------------------------------------- 2. burn captions
STAGE1="$TMP/stage1.mp4"
if (( DO_CAPTIONS )); then
  FONT_SIZE="$(awk -v h="$H" -v s="$FONT_SCALE" 'BEGIN{ printf "%d", (h*s < 12 ? 12 : h*s) }')"
  [[ -n "$MARGIN_V" ]] || MARGIN_V="$(awk -v h="$H" 'BEGIN{ printf "%d", h*0.18 }')"
  OUTLINE="$(awk -v f="$FONT_SIZE" 'BEGIN{ printf "%d", (f*0.09 < 2 ? 2 : f*0.09) }')"

  # ASS colours are &HAABBGGRR. 00 alpha = fully opaque.
  STYLE="FontName=${FONT},FontSize=${FONT_SIZE},Bold=1"
  STYLE="${STYLE},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000"
  STYLE="${STYLE},BorderStyle=1,Outline=${OUTLINE},Shadow=0"
  STYLE="${STYLE},Alignment=2,MarginL=60,MarginR=60,MarginV=${MARGIN_V}"

  # ffmpeg's SRT->ASS converter hardcodes PlayRes 384x288, and libass scales all
  # ASS units against that canvas — so a FontSize/MarginV expressed in real
  # pixels would be blown up ~6.7x and pushed off-frame. Convert to ASS first
  # and rewrite PlayRes to the true video size so those numbers mean pixels.
  SAFE_SRT="$TMP/subs.srt"
  [[ "$SRT" == "$SAFE_SRT" ]] || cp "$SRT" "$SAFE_SRT"

  RAW_ASS="$TMP/subs_raw.ass"
  SUBS="$TMP/subs.ass"
  ffmpeg -y -v error -i "$SAFE_SRT" "$RAW_ASS"
  awk -v w="$W" -v h="$H" '
    /^\[Script Info\]/       { print; print "PlayResX: " w; print "PlayResY: " h;
                              print "ScaledBorderAndShadow: yes"; next }
    /^PlayResX:/             { next }
    /^PlayResY:/             { next }
    /^ScaledBorderAndShadow:/ { next }
    { print }
  ' "$RAW_ASS" > "$SUBS"

  log "burning captions (${FONT} ${FONT_SIZE}px, ${MARGIN_V}px from bottom)"
  ffmpeg -y -v error -stats -i "$MAIN" \
    -vf "subtitles=${SUBS}:force_style='${STYLE}'" \
    -c:v libx264 -preset medium -crf "$CRF" -pix_fmt yuv420p \
    -c:a aac -b:a 192k -movflags +faststart "$STAGE1"
else
  log "captions skipped"
  STAGE1="$MAIN"
fi

if (( ! DO_OUTRO )); then
  # Never move when STAGE1 is the untouched source — that would consume the input.
  if [[ "$STAGE1" == "$MAIN" ]]; then
    cp -f "$MAIN" "$OUTPUT"
  else
    mv -f "$STAGE1" "$OUTPUT"
  fi
  log "done: $OUTPUT"
  exit 0
fi

# ------------------------------------------------------- 3. locate the outro
SAMPLE_DUR="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$SAMPLE")"
[[ -n "$SAMPLE_DUR" ]] || die "could not read duration of $SAMPLE"

if [[ -n "$OUTRO_START" ]]; then
  START="$OUTRO_START"
  log "outro starts at $START (explicit)"
elif [[ -n "$OUTRO_SECONDS" ]]; then
  START="$(awk -v d="$SAMPLE_DUR" -v n="$OUTRO_SECONDS" 'BEGIN{ s=d-n; print (s<0?0:s) }')"
  log "outro = last ${OUTRO_SECONDS}s of the sample (from ${START}s)"
else
  # Auto-detect: the last hard cut in the sample's closing stretch is almost
  # always where the end card begins.
  log "detecting the final scene cut in the sample"
  SEARCH_FROM="$(awk -v d="$SAMPLE_DUR" 'BEGIN{ s=d-20; print (s<0?0:s) }')"
  CUTS="$(ffmpeg -v error -ss "$SEARCH_FROM" -i "$SAMPLE" \
            -vf "select='gt(scene,0.35)',metadata=print:file=-" -an -f null - 2>/dev/null \
          | awk -F'pts_time:' '/pts_time/ { split($2, a, " "); print a[1] + '"$SEARCH_FROM"' }')" || true

  START="$(awk -v d="$SAMPLE_DUR" '
    { if ($1 <= d-1.0 && $1 >= d-15.0) last=$1 }
    END { if (last != "") print last }' <<<"$CUTS")"

  if [[ -n "$START" ]]; then
    log "final cut at ${START}s — using it as the outro start"
  else
    START="$(awk -v d="$SAMPLE_DUR" 'BEGIN{ s=d-3; print (s<0?0:s) }')"
    log "no clear cut found — falling back to the last 3s (from ${START}s)"
    log "override with --outro-seconds N or --outro-start T if that is wrong"
  fi
fi

# ------------------------------------------- 4. normalise the outro to match
# Scale to fit, pad to exact size: an outro shot at a different aspect ratio is
# letterboxed rather than stretched or cropped.
OUTRO="$TMP/outro.mp4"
VF="scale=${W}:${H}:force_original_aspect_ratio=decrease"
VF="${VF},pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=black"
VF="${VF},setsar=1,fps=${FPS},format=yuv420p"

SAMPLE_HAS_AUDIO=1
[[ -n "$(probe a:0 stream=index "$SAMPLE")" ]] || SAMPLE_HAS_AUDIO=0

log "normalising outro to ${W}x${H} @ ${FPS}fps"
if (( SAMPLE_HAS_AUDIO )) && [[ "$OUTRO_AUDIO" == keep ]]; then
  ffmpeg -y -v error -stats -ss "$START" -i "$SAMPLE" \
    -vf "$VF" \
    -c:v libx264 -preset medium -crf "$CRF" \
    -c:a aac -b:a 192k -ar "$AR" -ac "$ACH" "$OUTRO" 2>"$TMP/outro.log" || {
      cat "$TMP/outro.log" >&2; die "failed to build the outro clip"; }
else
  # Silent outro: synthesise matching silence so the concat has a uniform
  # stream layout.
  log "outro audio: silent"
  ffmpeg -y -v error -stats -ss "$START" -i "$SAMPLE" \
    -f lavfi -i "anullsrc=r=${AR}:cl=$([[ $ACH == 1 ]] && echo mono || echo stereo)" \
    -vf "$VF" -shortest -map 0:v:0 -map 1:a:0 \
    -c:v libx264 -preset medium -crf "$CRF" \
    -c:a aac -b:a 192k -ar "$AR" -ac "$ACH" "$OUTRO" 2>"$TMP/outro.log" || {
      cat "$TMP/outro.log" >&2; die "failed to build the outro clip"; }
fi

OUTRO_DUR="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUTRO")"
log "outro clip: ${OUTRO_DUR}s"

# ------------------------------------------------------------- 5. concatenate
log "joining main + outro"
if (( HAS_MAIN_AUDIO )); then
  ffmpeg -y -v error -stats -i "$STAGE1" -i "$OUTRO" \
    -filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]" \
    -map "[v]" -map "[a]" \
    -c:v libx264 -preset medium -crf "$CRF" -pix_fmt yuv420p \
    -c:a aac -b:a 192k -ar "$AR" -ac "$ACH" -movflags +faststart "$OUTPUT"
else
  ffmpeg -y -v error -stats -i "$STAGE1" -i "$OUTRO" \
    -filter_complex "[0:v:0][1:v:0]concat=n=2:v=1:a=0[v]" \
    -map "[v]" -map 1:a:0 \
    -c:v libx264 -preset medium -crf "$CRF" -pix_fmt yuv420p \
    -c:a aac -b:a 192k -movflags +faststart "$OUTPUT"
fi

FINAL_DUR="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUTPUT")"
log "done: $OUTPUT (${FINAL_DUR}s)"
if (( DO_CAPTIONS )) && [[ -n "$SRT" ]]; then
  cp "$SRT" "${OUTPUT%.*}.srt"
  log "captions also saved as ${OUTPUT%.*}.srt — edit and re-run with --srt to fix any wording"
fi
