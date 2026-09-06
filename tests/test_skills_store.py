from memory.repository import InMemoryRepository
from skills.models import LearnedSkillRecord, SkillStep, SkillStepKind
from skills.store import SkillLibrary


def _record(name: str = "utility.timer") -> LearnedSkillRecord:
    return LearnedSkillRecord(
        name=name,
        description="Toca um alarme depois de um tempo",
        parameters={"minutes": "float"},
        start_steps=[SkillStep(kind=SkillStepKind.WAIT, seconds_expr="minutes*60")],
        stop_steps=[SkillStep(kind=SkillStepKind.SPEAK, text="Cancelado")],
        stop_action_name=f"{name}.cancel",
        created_from_utterance="coloque um timer de 15 minutos",
    )


def test_add_and_get_by_name_round_trips() -> None:
    library = SkillLibrary(InMemoryRepository())
    library.add(_record())

    found = library.get_by_name("utility.timer")

    assert found is not None
    assert found.description == "Toca um alarme depois de um tempo"
    assert found.parameters == {"minutes": "float"}
    assert found.stop_action_name == "utility.timer.cancel"


def test_get_by_name_returns_none_when_absent() -> None:
    library = SkillLibrary(InMemoryRepository())
    assert library.get_by_name("does.not.exist") is None


def test_all_returns_every_learned_skill() -> None:
    library = SkillLibrary(InMemoryRepository())
    library.add(_record("utility.timer"))
    library.add(_record("utility.reminder"))

    names = {record.name for record in library.all()}

    assert names == {"utility.timer", "utility.reminder"}


def test_record_failure_increments_failure_count() -> None:
    library = SkillLibrary(InMemoryRepository())
    library.add(_record())

    library.record_failure("utility.timer")
    library.record_failure("utility.timer")

    assert library.get_by_name("utility.timer").failure_count == 2
