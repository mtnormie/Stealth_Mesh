#include "stealth_mesh.h"
#include <string.h>

bool EmbeddedMessageQueue::enqueue(const MeshFrame& frame) {
    if (count_ >= CAPACITY) {
        return false;
    }
    ring_[tail_] = frame;
    tail_ = (tail_ + 1) % CAPACITY;
    ++count_;
    return true;
}

bool EmbeddedMessageQueue::dequeue(MeshFrame& out_frame) {
    if (count_ == 0) {
        return false;
    }
    out_frame = ring_[head_];
    head_ = (head_ + 1) % CAPACITY;
    --count_;
    return true;
}
