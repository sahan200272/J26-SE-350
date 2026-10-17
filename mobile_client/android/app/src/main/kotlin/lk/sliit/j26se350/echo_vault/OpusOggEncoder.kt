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
 */
object OpusOggEncoder {
    private const val TIMEOUT_US = 10_000L

    /** What was used and produced, returned to Dart. */
    data class Result(
        val encoderName: String,
        val bitrate: Int,
        val inputSamples: Int,
        val packets: Int,
        val outputBytes: Long,
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
            var packets = 0
            while (true) {
                if (!inputDone) {
                    val index = codec.dequeueInputBuffer(TIMEOUT_US)
                    if (index >= 0) {
                        val buffer = codec.getInputBuffer(index)!!
                        buffer.clear()
                        val n = min(buffer.remaining() / bytesPerFrame * bytesPerFrame, pcm.size - offset)
                        val ptsUs = (offset / bytesPerFrame).toLong() * 1_000_000L / sampleRate
                        buffer.put(pcm, offset, n)
                        offset += n
                        inputDone = offset >= pcm.size
                        val flags = if (inputDone) MediaCodec.BUFFER_FLAG_END_OF_STREAM else 0
                        codec.queueInputBuffer(index, 0, n, ptsUs, flags)
                    }
                }

                val index = codec.dequeueOutputBuffer(info, TIMEOUT_US)
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
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                }
            }
            muxer.stop()
            muxerStarted = false
            return Result(name, bitrate, pcm.size / bytesPerFrame, packets, output.length())
        } finally {
            runCatching { codec.stop() }
            codec.release()
            if (muxerStarted) runCatching { muxer?.stop() }
            muxer?.release()
        }
    }
}
