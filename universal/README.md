# ST Universal Bridge 0.2 development candidate

기존 direct (wonjj)와 Rules 기반 HACS 통합을 그대로 유지하는 확장입니다.

## 지원
- 삼성 공개 Zigbee 공식 기반 12개 패키지: switch, motion, presence, contact, humidity, illuminance, power meter, button, dimmer remote, generic sensor, water leak, window treatment.
- wonjj 기존 패키지: 세탁실 창문/플러그 기본, 나머지는 --wonjj로 선택.
- 기타 공개 드라이버: 허용 라이선스, 정확한 GitHub 저장소/커밋/패키지 경로 및 검토한 src/init.lua Git blob SHA를 custom JSON에 등록한 뒤 자동 변환. 일반적인 st.zigbee 생성자와 단일 :run()만 지원. 모르는 구조는 중단.
- 비공개 드라이버 또는 변환 불가 기기: 기존 ST Local Bridge의 Rules 방식으로 등록. 자동 전환은 아직 구현하지 않음.
- 삼성 공식 기반은 SDK inject_capability_command로 하위 드라이버의 기존 명령 경로를 사용하고, 로컬 get_devices 목록을 3초마다 확인합니다. 원본 초기화/라이프사이클을 덮어쓰지 않음. SDK native default 속성/명령을 명시적으로 사용한 진입점은 Lua 경로로 변경. 하위 드라이버의 별도 native 설정과 허브 호환성은 실기 검증 필요.

## 사용
Windows Python 3.10+ 및 PyYAML.
    
    py -3 -m pip install PyYAML
    py -3 universal/inventory.py --out inventory.json
    py -3 universal/build.py --all-official --out universal-build

inventory는 CLI의 현재 기기 및 설치 드라이버 정보를 읽어 분류합니다. 정보가 부족하거나 원본 이름이 일치하지 않으면 rules_or_review로 분류; 소스 추측/자동 다운로드 없음. CLI 인증은 필요할 수 있습니다. --hub로 특정 허브 제한 가능. JSON 파일은 로컬에 보관하세요.

기타 공개 소스는 custom.example.json을 복사해 실제 값과 라이선스를 검토하고 --custom 경로를 지정합니다. 이 도구는 사용자 승인 없는 타사 소스 실행/배포/실제 기기 드라이버 변경을 수행하지 않습니다. 현재 설치 기기에 필요한 패키지 선택·빌드·전용 채널 생성/가입/설치까지 아래 스크립트로 처리합니다. 호환 기기 자체의 드라이버 변경은 수동 확인이 필요합니다.

    powershell -ExecutionPolicy Bypass -File .\universal\deploy.ps1 -PlanOnly
    powershell -ExecutionPolicy Bypass -File .\universal\deploy.ps1 -Install

전체 공식 기반 패키지와 기본 wonjj 두 패키지를 함께 설치하려면 -AllOfficial을 추가하세요. -Custom으로 검토된 JSON을 지정합니다. 설치 전에 목록 확인을 요청하며 실제 기기를 강제로 변경하거나 삭제하지 않습니다. 기존 direct/README.md의 MQTT 설정을 각 드라이버 계열의 대표 기기에서 수행합니다. 신규 기기는 해당 MQTT 드라이버에 매칭된 경우 자동으로 HA Discovery 등록됩니다.

## 제한
모든 설치 드라이버의 소스/원격 기기 접근은 SDK에서 제공하지 않습니다. 공개 소스 검색은 이름만으로 안전하게 자동 확정할 수 없습니다. 직접 MQTT는 수정된 드라이버가 담당하는 기기만 동작하며 원본 기본 드라이버 자체를 자동 패치하지 않습니다. 원본 라이선스/NOTICE 포함. 자동 빌드 검증은 삼성 허브 실기 검증과 다릅니다.

기존 HA 엔티티 ID의 계열 간 유지, 공통 MQTT 암호 1회 등록, 비공개 드라이버의 자동 Rules 전환, 제조사 임의 custom capability 자동 생성은 미구현입니다. 원본 드라이버 변경/재페어링 시 기존 SmartThings 자동화에 영향 가능. 클라우드 API 없이 전체 기기/드라이버를 지속적으로 검색하는 것은 지원되지 않습니다.

## 미래 타사 드라이버 등록 자동화

원본 GitHub 주소와 드라이버 디렉터리만 알면 커밋·파일 해시·라이선스·패키지 식별자를 자동 조회하고 등록할 수 있습니다.

    py -3 universal/register.py --search "driver name"
    py -3 universal/register.py --repo OWNER/REPO
    py -3 universal/register.py --repo OWNER/REPO --package path/to/driver
    py -3 universal/register.py --repo OWNER/REPO --package path/to/driver --approve

검색 결과는 후보일 뿐 동일 드라이버임을 보장하지 않습니다. --approve 전 원본 코드/라이선스를 검토하세요. 등록 정보는 custom.local.json에 로컬 저장됩니다. deploy.ps1은 이 파일을 자동 읽고 현재 설치 드라이버 이름과 일치하는 검토된 소스만 변환합니다. 설치는 별도 -Install 승인 후 진행됩니다. 공개 소스가 갱신됐는지 확인: `py -3 universal/register.py --check-updates`. 새 리비전은 검토 후 명시적으로 다시 등록해야 하며 자동 병합·자동 업로드하지 않습니다.

초기화 직후 설치 드라이버 목록이 비어 있거나 null이면 기본 5개 패키지로 부트스트랩합니다. `-Bootstrap`은 인식된 패키지에 기본 5개를 추가합니다. 드라이버 설치 목록을 확인한 후 승인해야 업로드합니다. CLI `--hub`는 설치를 내포하므로 `--install`과 함께 사용하지 않습니다.
