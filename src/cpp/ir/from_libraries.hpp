/**
 * @file from_libraries.hpp
 * @brief A pulseq_file built from the libraries pypulseqpp was read into.
 */

#ifndef PULSERVER_IR_FROM_LIBRARIES_HPP
#define PULSERVER_IR_FROM_LIBRARIES_HPP

#include <pybind11/pybind11.h>

#include "pulseq.h"

namespace pulserver
{

/**
 * Fill @p seq from one subsequence's libraries.
 *
 * @p libraries holds the arrays pulserver.ir reads a pypulseqpp Sequence
 * into, in the layout the parser produces. The file is left as a completed
 * parse: every library is marked read, so pulseq_file_free() releases it.
 */
void build_pulseq_file(pulseq_file &seq, const pybind11::dict &libraries);

} // namespace pulserver

#endif /* PULSERVER_IR_FROM_LIBRARIES_HPP */
