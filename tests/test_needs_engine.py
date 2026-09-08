"""NeedsEngine: hunger grows with real elapsed time, shrinks on feeding,
and never leaves [0, 1] -- same contract as EmotionalEngine.decay, just
one field and no baseline pull-back (hunger has no "resting point" other
than empty)."""
from memory.repository import InMemoryRepository
from emotions.needs import NeedsEngine, NeedsState, NeedsStore


def _engine() -> NeedsEngine:
    return NeedsEngine(NeedsStore(InMemoryRepository()))


def test_starts_at_default_hunger():
    engine = _engine()
    assert engine.state.hunger == NeedsState().hunger


def test_advance_grows_hunger_with_elapsed_time():
    engine = _engine()
    before = engine.state.hunger
    engine.advance(3600)  # one hour
    assert engine.state.hunger > before


def test_advance_never_exceeds_one():
    engine = _engine()
    engine.advance(3600 * 1000)  # absurdly long idle stretch
    assert engine.state.hunger == 1.0


def test_advance_with_no_elapsed_time_is_a_no_op():
    engine = _engine()
    before = engine.state.hunger
    engine.advance(0)
    assert engine.state.hunger == before


def test_feed_reduces_hunger():
    engine = _engine()
    engine.advance(3600)
    before = engine.state.hunger
    engine.feed()
    assert engine.state.hunger < before


def test_feed_never_goes_below_zero():
    engine = _engine()
    engine.feed(amount=5.0)
    assert engine.state.hunger == 0.0


def test_state_persists_across_stores_sharing_a_repository():
    repository = InMemoryRepository()
    first = NeedsEngine(NeedsStore(repository))
    first.advance(3600)
    first.save()

    second = NeedsEngine(NeedsStore(repository))
    assert second.state.hunger == first.state.hunger


def test_boredom_grows_when_not_engaged():
    engine = _engine()
    before = engine.state.boredom
    engine.advance(600, engaged=False)
    assert engine.state.boredom > before


def test_boredom_drains_while_engaged():
    engine = _engine()
    engine.advance(600, engaged=False)
    bored = engine.state.boredom
    engine.advance(600, engaged=True)
    assert engine.state.boredom < bored


def test_boredom_never_leaves_zero_one_range():
    engine = _engine()
    engine.advance(3600 * 1000, engaged=False)
    assert engine.state.boredom == 1.0
    engine.advance(3600 * 1000, engaged=True)
    assert engine.state.boredom == 0.0


def test_engaged_does_not_affect_hunger():
    not_engaged = _engine()
    not_engaged.advance(600, engaged=False)
    engaged = _engine()
    engaged.advance(600, engaged=True)
    assert not_engaged.state.hunger == engaged.state.hunger


def test_record_game_result_raises_game_skill_a_little():
    engine = _engine()
    before = engine.state.game_skill
    engine.record_game_result()
    assert engine.state.game_skill > before


def test_game_skill_never_exceeds_one():
    engine = _engine()
    for _ in range(1000):
        engine.record_game_result()
    assert engine.state.game_skill == 1.0


def test_last_read_subject_round_trips():
    engine = _engine()
    assert engine.consume_last_read_subject() is None
    engine.set_last_read_subject("gato")
    assert engine.state.last_read_subject == "gato"


def test_consume_last_read_subject_clears_it():
    engine = _engine()
    engine.set_last_read_subject("gato")
    assert engine.consume_last_read_subject() == "gato"
    assert engine.consume_last_read_subject() is None
