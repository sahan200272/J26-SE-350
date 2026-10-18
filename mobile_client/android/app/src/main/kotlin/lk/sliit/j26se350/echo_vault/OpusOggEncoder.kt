package lk.sliit.j26se350.echo_vault

import android.media.MediaCodec
import android.media.MediaCodecList
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.File
import kotlin.math.min

/**
 * Encodes 16-bit little-endian PCM to an Ogg Opus file with the platform encoder
 * (MediaCodec, audio/opus) and MediaMuxer (MUXER_OUTPUT_OGG). Both need API 29.
 *
 * Blocking: call it off the main thread.
 *
 * Loop (A5.1): each pass hands the codec every free input buffer without waiting, then blocks
 * (up to [OUTPUT_TIMEOUT_US]) for the next output buffer and drains every buffer that is ready.
 * It only blocks when the codec holds all input buffers or has all the input, so it must
 * produce output next. (The A4 loop waited 10 ms for an input buffer and took at most one
 * output buffer per pass: about one 20 ms packet per 10 ms wait, so encoding took about
 * 0.55 s per second of audio.)
 */
object OpusOggEncoder {
    /** Longest single wait for an output buffer; a wait that times out just starts a new pass. */
    private const val OUTPUT_TIMEOUT_US = 100_000L

    /** Gives up if the codec neither takes input nor produces output for this long. */
    private const val STALL_TIMEOUT_NS = 10_000_000_000L

    /** What was used and produced, returned to Dart. */
    data class Result(
        val encoderName: String,
        val bitrate: Int,
        val inputSamples: Int,
        val packets: Int,
        val outputBytes: Long,
        /** Output waits that ended without a buffer (diagnostic; ideally 0). */
        val outputWaitTimeouts: Int = 0,
    ) {
        fun toMap(): Map<String, Any> = mapOf(
            "encoder" to encoderName,
            "bitrate" to bitrate,
            "inputSamples" to inputSamples,
            "packets" to packets,
            "outputBytes" to outputBytes,
        )
    }

    fun encode(pcm: ByteArray, sampleRate: Int, channels: Int, bitrate: Int, output: File): Result {
        val bytesPerFrame = 2 * channels
        require(pcm.size % bytesPerFrame == 0) { "PCM length ${pcm.size} is not whole samples" }
        val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_OPUS, sampleRate, channels)
        format.setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
        val name = MediaCodecList(MediaCodecList.REGULAR_CODECS).findEncoderForFormat(format)
            ?: throw IllegalStateException("No Opus encoder for $sampleRate Hz, $channels ch, $bitrate bit/s")

        output.parentFile?.mkdirs()
        val codec = MediaCodec.createByCodecName(name)
        var muxer: MediaMuxer? = null
        var muxerStarted = false
        try {
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            codec.start()
            muxer = MediaMuxer(output.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_OGG)

            val info = MediaCodec.BufferInfo()
            var track = -1
            var offset = 0
            var inputDone = false
            var outputDone = false
            var packets = 0
            var waitTimeouts = 0
            var lastProgress = System.nanoTime()
            while (!outputDone) {
                // 1. Every free input buffer, without waiting.
                while (!inputDone) {
                    val index = codec.dequeueInputBuffer(0)
                    if (index < 0) break
                    val buffer = codec.getInputBuffer(index)!!
                    buffer.clear()
                    val n = min(buffer.remaining() / bytesPerFrame * bytesPerFrame, pcm.size - offset)
                    val ptsUs = (offset / bytesPerFrame).toLong() * 1_000_000L / sampleRate
                    buffer.put(pcm, offset, n)
                    offset += n
                    inputDone = offset >= pcm.size
                    val flags = if (inputDone) MediaCodec.BUFFER_FLAG_END_OF_STREAM else 0
                    codec.queueInputBuffer(index, 0, n, ptsUs, flags)
                    lastProgress = System.nanoTime()
                }

                // 2. Block for the next output buffer, then drain all that are ready.
                var timeoutUs = OUTPUT_TIMEOUT_US
                while (!outputDone) {
                    val index = codec.dequeueOutputBuffer(info, timeoutUs)
                    if (index == MediaCodec.INFO_TRY_AGAIN_LATER) {
                        if (timeoutUs > 0) waitTimeouts++
                        break
                    }
                    timeoutUs = 0
                    if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                        // The output format carries the Opus header (csd-0..2) the muxer needs.
                        track = muxer.addTrack(codec.outputFormat)
                        muxer.start()
                        muxerStarted = true
                    } else if (index >= 0) {
                        val buffer = codec.getOutputBuffer(index)!!
                        val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
                        if (!isConfig && info.size > 0) {
                            check(muxerStarted) { "Encoder output before its format" }
                            buffer.position(info.offset)
                            buffer.limit(info.offset + info.size)
                            muxer.writeSampleData(track, buffer, info)
                            packets++
                        }
                        codec.releaseOutputBuffer(index, false)
                        lastProgress = System.nanoTime()
                        outputDone = info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                    }
                }
                check(System.nanoTime() - lastProgress < STALL_TIMEOUT_NS) {
                    "Opus encoder made no progress for ${STALL_TIMEOUT_NS / 1_000_000_000} s"
                }
            }
            muxer.stop()
            muxerStarted = false
            return Result(name, bitrate, pcm.size / bytesPerFrame, packets, output.length(), waitTimeouts)
        } finally {
            runCatching { codec.stop() }
            codec.release()
            if (muxerStarted) runCatching { muxer?.stop() }
            muxer?.release()
        }
    }
}
