from crawler.notifier import Notifier, StockTracker


class FakeNotifier(Notifier):
    def __init__(self):
        self.sent = []

    def notify(self, title, message):
        self.sent.append((title, message))


def result(in_stock, status="success"):
    return [
        {
            "product_id": "p1",
            "url": "u",
            "status": status,
            "varieties": [{"variety": "v", "in_stock": in_stock}] if status == "success" else [],
        }
    ]


def run(seq):
    n = FakeNotifier()
    t = StockTracker(n)
    for s in seq:
        t.update(result(s))
    return len(n.sent)


def test_transitions():
    assert run([True, True]) == 1  # first sight counts as restock, then none
    assert run([True, False]) == 1
    assert run([False, True]) == 1
    assert run([False, False]) == 0
    assert run([False, True, False, True]) == 2


def test_single_message_for_multiple_varieties():
    n = FakeNotifier()
    t = StockTracker(n)
    t.update(
        [
            {
                "product_id": "p1",
                "title": "Matcha Tin",
                "url": "u",
                "status": "success",
                "varieties": [
                    {"variety": "a", "in_stock": True},
                    {"variety": "b", "in_stock": True},
                    {"variety": "c", "in_stock": False},
                ],
            }
        ]
    )
    assert len(n.sent) == 1
    msg = n.sent[0][1]
    assert "Matcha Tin - a: IN STOCK" in msg and "b: IN STOCK" in msg and "c: out of stock" in msg


def test_error_keeps_state():
    n = FakeNotifier()
    t = StockTracker(n)
    t.update(result(True))
    t.update(result(False, status="error"))
    t.update(result(True))
    assert len(n.sent) == 1
