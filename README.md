# ST Local Bridge 1.0 RC1

기존 SmartThings Zigbee/Z-Wave/Matter 로컬 기기를 재페어링 없이 Home Assistant로 연결하는 자체 Edge MQTT 브리지. 삼성 TV 내장 허브의 v0.3.1에서 MQTT 연결, 실제 세탁실 창문 닫기, 상태 수신, 10개 Local Rules 등록까지 실기 확인됨. 새 1.0 RC1 관리자 구조와 확장 기능은 별도 실기 검증이 필요합니다.

## 최초 설치 (한 번)

1. HA Mosquitto 및 MQTT 통합 활성화. MQTT 인증 계정 사용, LAN에만 1883 노출.
2. Windows PC에서 SmartThings CLI 인증 완료 후 [ZIP 다운로드](https://github.com/cleverk2000-code/ST/archive/refs/heads/main.zip) 및 압축 해제.
3. PowerShell에서 압축 해제한 저장소 루트로 이동해 실행:

       powershell -ExecutionPolicy Bypass -File .\tools\deploy_manager.ps1

   새 전용 채널 생성/허브 가입은 처음 한 번만. CLI 기본 채널이 이전 삭제 채널이면 config:reset으로 해당 기본값을 다시 선택하십시오. --install은 패키지/채널 할당/허브 설치를 함께 진행합니다. 삼성 서버 계정 인증/배포는 사용자가 해야 합니다.
4. SmartThings 앱에서 주변 기기 검색 1회. **ST Local Manager** 설정에서 HA VM LAN IPv4, 1883, MQTT 계정, Enable bridge=ON 입력. 계정은 이 관리자 하나에만 입력. MQTT 암호는 TLS 없는 신뢰 LAN용 전용 계정 사용.
5. HACS 사용자 지정 저장소에 이 저장소를 Integration으로 추가/업데이트하고 HA 재시작. 통합 추가 → ST Local Bridge → 통합 관리자 → SmartThings PAT 입력 → 관리자 선택. MQTT 연결 검증.
6. 해당 통합 구성(Options) → 일괄 추가 → PAT 입력 → 기기 복수 선택. 실제 UUID 복사, 기기별 PowerShell 실행 불필요. Rules의 executionLocation이 Local인 경우에만 활성화. HA MQTT Discovery로 엔티티 생성.

PAT 발급: https://account.smartthings.com/tokens (기기 읽기/삭제 및 Rules 읽기/쓰기/삭제, 필요한 위치 권한). 신규 PAT는 24시간 유효. HA에 저장하지 않으며 초기 설정/추가/삭제에만 사용. 평상시 제어는 클라우드 API를 사용하지 않음. 설정 UI의 첫 조회와 일괄 추가가 별도이므로 같은 PAT를 재사용해도 됩니다.

## 기기 지원

main 컴포넌트의 로컬 기기만 지원. switch, light 및 brightness, windowShade 및 position/stop, motion, contact, presence, water, temperature, humidity, battery, button(pushed/held/double). 안전을 위해 잠금·가스밸브·난방·차고문 등은 제외. 조명 색상, multi-component, 팬 속도는 미지원. 각 기기당 가상 프록시 1개와 Local Rules가 자동 생성되며 기존 물리 기기 드라이버는 변경하지 않음. 최대 프록시 64개, 실제 허브/Rules API 제한에 따라 더 적을 수 있음.

## 복구/삭제

구성 → 일괄 추가에서 failed 기기를 선택해 재시도. 부분 성공 기록은 HA Store에 보존. 이미 등록된 Rule을 재사용하려면 이름과 내용 검증. 상태 재동기화 옵션은 PAT 불필요. 구성 → 기기 및 Rules 삭제에서 먼저 전체 선택 후 삭제. 실제 기기 ID와 가상 프록시 ID를 대조하고 생성된 Rules/Discovery만 삭제. 통합 자체 삭제 시 토큰이 없으므로 서버 Rules/가상 기기 자동 삭제를 보장할 수 없음: 반드시 옵션에서 삭제 먼저. 삭제된 통합의 journal은 재등록 후 정리 가능.

## 로컬 동작 및 한계

관리자 단일 MQTT 세션, clean session, Last Will, 15초 heartbeat, 자동 재연결 1~30초, retained 제어 메시지 거부. 상태는 Rule이 보고한 물리 상태만 사용. 재연결 시 필드 availability를 offline으로 초기화하고 sync Rule을 통해 재조회한 값으로 복구. sync는 허브가 보유한 물리 기기의 마지막 capability 상태이며 물리 장치에 직접 새 측정 요청을 하지 않음. MQTT/Rules가 Local이라고 실제 장치가 살아있다는 뜻은 아님. 기존 공식 통합을 유지하며 안전한 환경에서 기기 하나로 먼저 확인. 위치·밝기·숫자 보고는 동적 RuleOperand를 사용하며 새 실기 검증 필요. 사용자 테스트 이후 Wi-Fi/LAN을 유지하고 WAN만 차단해 양방향 작동 확인.

## 검증

Python contract unit tests, Lua packet/transport/manager contract tests, GitHub Actions. 실제 삼성 서버 등록과 새 관리자 구조, 자동 생성 및 HA UI 동작은 RC 단계에서 실기 검증 필요. 정식 안정판이라고 주장하지 않습니다.

기존 검증용 v0.3.1 코드는 [legacy-v0.3.1](https://github.com/cleverk2000-code/ST/tree/legacy-v0.3.1)에 보존되어 있습니다. 기존 수동 등록 경로도 남겨둡니다.

참고: https://developer.smartthings.com/docs/automations/rules · https://developer.smartthings.com/docs/devices/hub-connected/driver-channels/ · https://www.home-assistant.io/integrations/mqtt/
