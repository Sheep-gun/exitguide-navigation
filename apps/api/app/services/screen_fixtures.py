from app.services.types import ExtractedElement, ExtractedScreen


def cancellation_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="구독 해지",
        text="혜택 유지, 해지 계속하기, 이번 달 혜택 종료 안내",
        elements=[
            ExtractedElement(
                id="primary_retention_button",
                label="혜택 유지하기",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="secondary_cancel_button",
                label="해지 계속하기",
                element_type="button",
                prominence=1,
            ),
            ExtractedElement(
                id="loss_warning",
                label="이번 달 혜택이 사라집니다",
                element_type="text",
                prominence=2,
            ),
        ],
    )


def cancellation_confirmation_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="구독 해지 확인",
        text="해지 완료, 다음 결제 없음, 돌아가기",
        elements=[
            ExtractedElement(
                id="complete_cancellation_button",
                label="해지 완료하기",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="no_next_billing_notice",
                label="해지 후 다음 결제는 없습니다",
                element_type="text",
                prominence=2,
            ),
            ExtractedElement(
                id="back_button",
                label="돌아가기",
                element_type="button",
                prominence=1,
            ),
        ],
    )


def cancellation_pause_offer_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="구독 일시정지 제안",
        text="한 달 일시정지 유지, 해지 계속하기, 이후 결제 재개",
        elements=[
            ExtractedElement(
                id="pause_subscription_button",
                label="한 달만 일시정지하기",
                element_type="button",
                prominence=2,
            ),
            ExtractedElement(
                id="secondary_cancel_button",
                label="해지 계속하기",
                element_type="button",
                prominence=1,
            ),
            ExtractedElement(
                id="billing_resume_notice",
                label="일시정지가 끝나면 결제가 재개됩니다",
                element_type="text",
                prominence=1,
            ),
        ],
    )


def trial_renewal_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="무료 체험 자동 결제",
        text="내일 체험 자동 결제, 체험 연장, 지금 체험 해지, 월 결제 금액",
        elements=[
            ExtractedElement(
                id="renewal_warning",
                label="내일부터 월 12,900원이 결제됩니다",
                element_type="text",
                prominence=3,
                monetary_impact=True,
            ),
            ExtractedElement(
                id="extend_trial_button",
                label="7일 더 무료로 이용하기",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="cancel_trial_button",
                label="지금 체험 해지하기",
                element_type="button",
                prominence=1,
            ),
        ],
    )


def trial_discount_retention_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="무료 체험 할인 제안",
        text="할인으로 체험 유지, 매월 결제, 지금 체험 해지",
        elements=[
            ExtractedElement(
                id="discount_retention_button",
                label="50% 할인으로 계속 이용하기",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="renewal_warning",
                label="할인 후 월 12,900원으로 갱신됩니다",
                element_type="text",
                prominence=2,
                monetary_impact=True,
            ),
            ExtractedElement(
                id="cancel_trial_button",
                label="지금 체험 해지하기",
                element_type="button",
                prominence=1,
            ),
        ],
    )


def trial_success_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="무료 체험 해지 완료",
        text="체험 해지 완료, 다음 결제 없음, 확인",
        elements=[
            ExtractedElement(
                id="trial_canceled_notice",
                label="무료 체험이 해지되었습니다",
                element_type="text",
                prominence=3,
            ),
            ExtractedElement(
                id="no_next_billing_notice",
                label="다음 결제는 발생하지 않습니다",
                element_type="text",
                prominence=2,
            ),
            ExtractedElement(
                id="confirm_button",
                label="확인",
                element_type="button",
                prominence=2,
            ),
        ],
    )


def checkout_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="결제",
        text="주문 합계, 배송 보험 선택됨, 멤버십 체험 시작, 결제하기",
        elements=[
            ExtractedElement(
                id="shipping_insurance",
                label="배송 보험 +2,900원",
                element_type="checkbox",
                default_selected=True,
                monetary_impact=True,
                optional=True,
            ),
            ExtractedElement(
                id="membership_trial",
                label="멤버십 무료 체험 시작, 이후 매월 결제",
                element_type="checkbox",
                default_selected=True,
                monetary_impact=True,
                optional=True,
            ),
            ExtractedElement(
                id="pay_now",
                label="결제하기",
                element_type="button",
                prominence=3,
            ),
        ],
    )


def donation_addon_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="포인트 기부 추가",
        text="주문 합계, 선택 포인트 기부 선택됨, 결제하기",
        elements=[
            ExtractedElement(
                id="points_donation",
                label="보유 포인트를 캠페인에 기부",
                element_type="checkbox",
                default_selected=True,
                optional=True,
            ),
            ExtractedElement(
                id="pay_now",
                label="결제하기",
                element_type="button",
                prominence=3,
            ),
        ],
    )


def warranty_addon_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="연장 보증 추가",
        text="주문 합계, 연장 보증 선택됨, 결제하기",
        elements=[
            ExtractedElement(
                id="extended_warranty",
                label="연장 보증 +9,900원",
                element_type="checkbox",
                default_selected=True,
                monetary_impact=True,
                optional=True,
            ),
            ExtractedElement(
                id="pay_now",
                label="결제하기",
                element_type="button",
                prominence=3,
            ),
        ],
    )


def clean_checkout_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="깨끗한 결제",
        text="주문 합계, 선택 배송 보험 해제됨, 멤버십 체험 해제됨, 결제하기",
        elements=[
            ExtractedElement(
                id="shipping_insurance",
                label="배송 보험 +2,900원",
                element_type="checkbox",
                default_selected=False,
                monetary_impact=True,
                optional=True,
            ),
            ExtractedElement(
                id="membership_trial",
                label="멤버십 무료 체험 시작, 이후 매월 결제",
                element_type="checkbox",
                default_selected=False,
                monetary_impact=True,
                optional=True,
            ),
            ExtractedElement(
                id="pay_now",
                label="결제하기",
                element_type="button",
                prominence=3,
            ),
        ],
    )


def consent_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="약관 동의",
        text="전체 동의, 필수 약관, 선택 마케팅 메시지, 계속",
        elements=[
            ExtractedElement(
                id="agree_all",
                label="전체 동의",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="optional_marketing",
                label="선택 마케팅 메시지 수신",
                element_type="checkbox",
                default_selected=True,
                optional=True,
            ),
            ExtractedElement(
                id="required_terms",
                label="필수 서비스 약관",
                element_type="checkbox",
            ),
        ],
    )


def separated_marketing_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="분리된 선택 동의",
        text="필수 약관 선택됨, 선택 마케팅 해제됨, 계속",
        elements=[
            ExtractedElement(
                id="required_terms",
                label="필수 서비스 약관",
                element_type="checkbox",
                default_selected=True,
            ),
            ExtractedElement(
                id="optional_marketing",
                label="선택 마케팅 메시지 수신",
                element_type="checkbox",
                default_selected=False,
                optional=True,
            ),
            ExtractedElement(
                id="continue_button",
                label="계속",
                element_type="button",
                prominence=2,
            ),
        ],
    )


def required_terms_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="필수 약관",
        text="필수 서비스 약관, 필수 개인정보 약관, 계속",
        elements=[
            ExtractedElement(
                id="required_terms",
                label="필수 서비스 약관",
                element_type="checkbox",
                default_selected=True,
            ),
            ExtractedElement(
                id="required_privacy",
                label="필수 개인정보 처리방침",
                element_type="checkbox",
                default_selected=True,
            ),
            ExtractedElement(
                id="continue_button",
                label="계속",
                element_type="button",
                prominence=2,
            ),
        ],
    )


def account_deletion_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="계정 탈퇴",
        text="계정 유지, 계정 탈퇴 계속하기, 데이터 삭제 안내",
        elements=[
            ExtractedElement(
                id="keep_account_button",
                label="계정 유지하기",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="delete_account_button",
                label="계정 탈퇴 계속하기",
                element_type="button",
                prominence=1,
            ),
            ExtractedElement(
                id="data_loss_warning",
                label="프로필과 저장 데이터가 삭제될 수 있습니다",
                element_type="text",
                prominence=2,
            ),
        ],
    )


def account_deletion_confirmation_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="계정 탈퇴 확인",
        text="계정 탈퇴 완료, 데이터 복구 불가, 돌아가기",
        elements=[
            ExtractedElement(
                id="complete_account_deletion_button",
                label="계정 탈퇴 완료하기",
                element_type="button",
                prominence=3,
            ),
            ExtractedElement(
                id="data_recovery_warning",
                label="일부 데이터는 복구할 수 없습니다",
                element_type="text",
                prominence=2,
            ),
            ExtractedElement(
                id="back_button",
                label="돌아가기",
                element_type="button",
                prominence=1,
            ),
        ],
    )


def neutral_context_screen() -> ExtractedScreen:
    return ExtractedScreen(
        title="일반 콘텐츠",
        text="커뮤니티 댓글이나 게시글처럼 가입, 결제, 해지, 동의 행동을 요구하지 않는 콘텐츠",
        elements=[
            ExtractedElement(
                id="content_text",
                label="일반 댓글 또는 게시글 내용",
                element_type="text",
                prominence=2,
            ),
            ExtractedElement(
                id="passive_reaction",
                label="좋아요 또는 답글 같은 선택 행동",
                element_type="button",
                prominence=1,
                optional=True,
            ),
        ],
    )


SCREEN_FIXTURES = {
    "cancel": cancellation_screen,
    "cancel_confirmation": cancellation_confirmation_screen,
    "cancel_pause_offer": cancellation_pause_offer_screen,
    "trial": trial_renewal_screen,
    "trial_discount_retention": trial_discount_retention_screen,
    "trial_success": trial_success_screen,
    "checkout": checkout_screen,
    "checkout_donation": donation_addon_screen,
    "checkout_warranty": warranty_addon_screen,
    "checkout_clean": clean_checkout_screen,
    "consent": consent_screen,
    "marketing_separated": separated_marketing_screen,
    "required_terms": required_terms_screen,
    "account_delete": account_deletion_screen,
    "account_delete_confirmation": account_deletion_confirmation_screen,
    "neutral_context": neutral_context_screen,
}
