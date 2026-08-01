from app.services.navigation_goal_robustness import metamorphic_goal_variants


def main() -> None:
    korean = metamorphic_goal_variants("구독을 해지해줘", mode="full")
    english = metamorphic_goal_variants("cancel my subscription", mode="full")
    assert len(korean) == 4
    assert len(english) == 4
    assert korean[0][1].startswith("유튜브에서 ")
    assert english[0][1].startswith("please ")
    assert any(value.strip().endswith("...") for _, value in korean)
    assert any(value.strip().endswith("...") for _, value in english)
    print("navigation goal robustness checks ok")


if __name__ == "__main__":
    main()
