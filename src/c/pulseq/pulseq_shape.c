/**
 * @file pulseq_shape.c
 * @brief The Pulseq run-length shape codec.
 *
 * A stored shape is the derivative of its samples, with a repeat count after
 * any value that occurs three times running. Decompression is the inverse,
 * and is what every reader of a shape goes through.
 */

#include <math.h>

#include "pulseq_internal.h"

int pulseq_decompress_shape(pulseq_shape *result, const pulseq_shape *encoded, PULSEQ_REAL scale)
{
    int i, rep;
    const PULSEQ_REAL *packed;
    int num_packed, num_samples;
    int count_pack = 1;
    int count_unpack = 1;
    PULSEQ_REAL *unpacked;

    if (!encoded || !result)
        return 0;
    if (!encoded->samples && encoded->num_uncompressed_samples > 0)
        return 0;

    packed = encoded->samples;
    num_packed = encoded->num_samples;
    num_samples = encoded->num_uncompressed_samples;

    /* Uncompressed — copy */
    if (encoded->num_samples == encoded->num_uncompressed_samples)
    {
        result->num_samples = encoded->num_samples;
        result->num_uncompressed_samples = encoded->num_uncompressed_samples;
        result->samples = (PULSEQ_REAL *)PULSEQ_ALLOC(sizeof(PULSEQ_REAL) * encoded->num_samples);
        if (!result->samples)
            return 0;
        for (i = 0; i < encoded->num_samples; ++i)
            result->samples[i] = encoded->samples[i] * scale;
        return 1;
    }

    unpacked = (PULSEQ_REAL *)PULSEQ_ALLOC(sizeof(PULSEQ_REAL) * num_samples);
    if (!unpacked)
        return 0;

    while (count_pack < num_packed)
    {
        if (packed[count_pack - 1] != packed[count_pack])
        {
            unpacked[count_unpack - 1] = packed[count_pack - 1];
            count_pack++;
            count_unpack++;
        }
        else
        {
            rep = (int)(packed[count_pack + 1]) + 2;
            if (fabs(packed[count_pack + 1] + 2 - (PULSEQ_REAL)rep) > 1e-6f)
            {
                PULSEQ_FREE(unpacked);
                return 0;
            }
            for (i = count_unpack - 1; i <= count_unpack + rep - 2; i++)
                unpacked[i] = packed[count_pack - 1];
            count_pack += 3;
            count_unpack += rep;
        }
    }
    if (count_pack == num_packed)
        unpacked[count_unpack - 1] = packed[count_pack - 1];

    /* Cumulative sum */
    for (i = 1; i < num_samples; i++)
        unpacked[i] += unpacked[i - 1];

    /* Scale */
    for (i = 0; i < num_samples; i++)
        unpacked[i] *= scale;

    result->num_samples = num_samples;
    result->num_uncompressed_samples = num_samples;
    result->samples = unpacked;
    return 1;
}
