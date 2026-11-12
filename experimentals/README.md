# 실험용 작업 폴더

이 폴더는 **`experimental` 브랜치에서만 추적·업로드**합니다. 기능 검증, 모델 비교, 임시 프로토타입 등 실험별로 하위 폴더를 만들어 사용하세요. Python 실행에는 프로젝트와 동일한 Miniconda `translator` 환경을 사용합니다.

## 작업하고 업로드하기

프로젝트 루트의 PowerShell에서 실행합니다.

```powershell
git switch experimental
# experimentals/ 아래에 실험 파일 작성
git add experimentals
git commit -m "Add experiment"
git push origin experimental
```

실험 파일을 커밋한 뒤 `git switch main`으로 돌아가면 해당 브랜치에 없는 추적 파일은 작업 폴더에서도 사라집니다. 다시 `git switch experimental`로 돌아오면 복원됩니다. 커밋하지 않은 작업은 먼저 저장하세요.

## 브랜치 구분

- `main`: 제품 코드와 사용자 설명서. `experimentals/`는 무시합니다.
- `experimental`: 실험 파일과 실험에 필요한 변경. 이 폴더를 포함한 브랜치 전체를 `main`에 합치지 않습니다.
- 제품에 필요한 일반 코드 수정은 실험 파일과 별도 커밋으로 만들어 선택적으로 반영합니다.

API 키·영상·모델·실행 결과에 대한 기존 제외 규칙은 유지됩니다. 실험별 목적·실행 방법·결과 요약은 각 하위 폴더의 README에 남기세요.

현재 PC에는 다른 브랜치로 실험 파일이 올라가지 않도록 Git 훅을 활성화했습니다. 새로 clone한 PC에서는 아래 명령을 한 번 실행해야 합니다.

```powershell
git config --local core.hooksPath .githooks
```

훅은 로컬 실수 방지 기능이며, 서버 측 강제 정책은 아닙니다. 상세 동작은 [개발 문서](../docs/development.md#11-실험용-브랜치와-폴더)를 참고하세요.
