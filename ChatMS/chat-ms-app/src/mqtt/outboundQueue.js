export class OutboundQueue {
  constructor() {
    this._items = []
  }

  enqueue(item) {
    this._items.push(item)
    return item
  }

  removeById(id) {
    const idx = this._items.findIndex((x) => x.id === id)
    if (idx >= 0) this._items.splice(idx, 1)
  }

  peekAll() {
    return [...this._items]
  }

  get size() {
    return this._items.length
  }

  clear() {
    this._items = []
  }
}

export function createQueueItem({ channel, recipientId, text, timestamp }) {
  return {
    id: `q-${timestamp}-${Math.random().toString(36).slice(2)}`,
    channel,
    recipientId: recipientId ?? null,
    text,
    timestamp,
  }
}
