"""레이어 파이프라인 API 라우터 패키지.

이 패키지의 `layer_ops`는 관리자 소유 Palimpsest squashfs 레이어
빌드·artifact/profile·소비 파이프라인이며 `main.py` 가 직접 마운트한다.

2세대 union(`layers.py`, `/api/v1/union`)은 인프라가 배포된 적 없어 폐기됐다.
디렉터리 이름 `union` 은 감사 매핑(`union_layer`)·DB 테이블명과의 정합을 위해 유지한다.
관계는 `docs/palimpsest.md` 참조.
"""
