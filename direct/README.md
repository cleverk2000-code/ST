# ST Direct MQTT — 개발 후보 0.1.0

Rules 없이 실제 Zigbee 드라이버에서 MQTT를 직접 송수신하는 별도 프로젝트입니다. 기존 ST Local Bridge 1.0 (Rules 방식)는 그대로 유지됩니다. 삼성 API 호출이나 PAT 없이 **설치된 호환 드라이버가 관리하는 기기**를 HA MQTT Discovery로 연동하는 것이 목표입니다.

## 구성

- 원본 [wonjj6768 드라이버](https://github.com/wonjj6768/smartthings-zigbee-edge-drivers)의 MIT 라이선스 고정 리비전 `2c97fe1729dc74ee598737a98296ae7c3b902257`을 사용합니다. 원본 Zigbee 모델 매핑, 프로필, 핑거프린트와 사용자 설정을 보존합니다.
- 원본 초기화 템플릿에 MQTT 라이프사이클 래퍼 한 줄을 삽입합니다. 새로운 packageKey로 배포하고 Zigbee+LAN 권한을 선언합니다. 원본 드라이버나 기기를 덮어쓰지 않습니다. SDK의 두 권한 동시 사용 및 인스턴스 이벤트 훅은 TV 허브 실기 검증 필요.
- MQTT 3.1.1, 인증된 사설 IP TCP, Last Will, 15초 heartbeat, 1~30초 재연결, clean session, 구독 시 전달되는 retained 명령 거부. 실제 Zigbee 명령은 기존 핸들러를 기기 스레드에서 실행합니다. 2초 이상 지연된 큐 명령은 폐기합니다.
- 등록은 별도 HA 통합 없이 HA 기본 MQTT Discovery로 자동 수행. 원본 드라이버가 내보내는 상태를 미러링하며 원본의 낙관적 상태 보고도 그대로 반영될 수 있습니다. 재연결/HA 시작 시 SmartThings 캐시 상태를 재전송합니다. 30초 캐시 보완 동기화, 버튼은 개별 이벤트만 송신(재연결 시 재생하지 않음).
- 플러그/스위치, 밝기/색온도/HS 조명, 창문 개폐/정지/위치, 전력/전압/전류/전력량, 온습도/조도/배터리/접촉/모션/재실/누수/버튼을 표준 capability에 맞추어 노출합니다. 실제 지원은 원본 모델과 프로필, 핸들러에 따라 다릅니다. 다중 component는 개별 HA 엔티티로 구분합니다. 안전 관련 제어(잠금, 가스, 난방, 차고문, 경보)는 제외합니다. 버튼 이벤트 훅이 실패하면 버튼 엔티티를 노출하지 않습니다.

## 설치 (실기 검증 전)

Windows에서 Python 3.10+ 및 SmartThings CLI 필요. PyYAML 설치: `py -3 -m pip install PyYAML`.

저장소 루트에서 아래를 실행하면 원본 고정 리비전 ZIP을 받아 **세탁실 창문(EF00 Covers 2)과 일반 플러그(ZCL Plugs)** 두 패키지를 생성합니다. 기본은 빌드만 하며 업로드하지 않습니다.

    powershell -ExecutionPolicy Bypass -File .\direct\deploy.ps1

원본 실제 모델 찾기:

    py -3 direct/build.py --find _TZ3210_5rta89nj TS0601
    py -3 direct/build.py --list

배포 전 전용 채널 생성 및 허브 가입은 삼성 CLI 계정에서 최초 한 번 수행:

    smartthings edge:channels:create
    smartthings edge:channels:enroll

생성한 채널 ID, 허브 ID를 지정해 배포:

    powershell -ExecutionPolicy Bypass -File .\direct\deploy.ps1 -Install -HubId YOUR_HUB_UUID -ChannelId YOUR_CHANNEL_UUID

다른 패키지는 `-Packages`에 목록을 지정해 추가 빌드/배포. 처음부터 전 패키지를 설치하지 마세요. 기존 Zigbee 기기 또는 원본 채널을 삭제하지 않습니다.

SmartThings 앱에서 호환 기기 → 드라이버 변경 → ST MQTT 계열을 선택(지원되는 경우). **원본 프로젝트는 재페어링을 권장합니다.** 재페어링 없이 변경 가능한지 먼저 확인하고 기존 자동화/기기 설정을 백업하세요. 정상 변경 시 먼저 비위험 조명/플러그로 검증하세요. 기기 자체에 기존 MQTT 설정은 없으며, 같은 패키지에 속한 기기 중 하나에서 아래 설정만 입력합니다.

- Use this device for driver MQTT settings = ON
- MQTT broker IPv4 = HA LAN IP (기본 192.168.0.19)
- MQTT broker port = 1883
- MQTT username/password = 전용 MQTT 계정
- MQTT site identifier = home (복수 허브는 서로 다른 값)
- Export to HA MQTT = ON (기기별 제외는 OFF)

같은 드라이버 패키지의 이후 기기는 자동 등록됩니다. 별도 패키지(예: 창문과 플러그)마다 설정을 한 번 해야 합니다. 설정 담당 기기가 제거되면 다른 기기에서 설정해야 합니다. 서로 다른 접속 정보가 설정되어 있으면 MQTT 연결을 중단하며 기존 Zigbee 동작은 유지하도록 설계했습니다. MQTT 암호는 GitHub 소스 및 빌드 패키지에 넣지 않습니다. LAN TCP는 TLS가 아니므로 인터넷에 개방하지 마세요.

HA에서는 MQTT 통합만 활성화하면 됩니다. Rules, 가상 브리지, PAT, 기존 ST Local Bridge HACS 통합은 필요하지 않습니다. 기존 통합과 병행하면 엔티티가 중복될 수 있으니 확인 후 자동화 대상만 변경하세요.

## 알려진 한계

- 최초 드라이버 배포/신규 기기 페어링 자체는 SmartThings 플랫폼을 사용합니다. 정책 변경과 무관하다고 보장할 수 없습니다.
- 연결 상태는 드라이버 MQTT 및 등록 상태를 나타내며 개별 배터리 기기의 실시간 생존 여부를 보증하지 않습니다. 초기 상태는 SmartThings 캐시의 마지막 값일 수 있습니다.
- MQTT QoS0 상태 전송/QoS1 명령 수신. 중복 QoS1 명령은 절대값 명령 중심으로 제한되지만 중복 pause 가능. 오프라인 버튼 이벤트는 재생하지 않습니다.
- 기기 제거/프로필 변경 시 기존 Discovery를 지웁니다. 허브가 오프라인인 상태에서 마지막 기기를 삭제하거나 드라이버가 즉시 종료된 경우 브로커에 잔존 retained discovery를 자동 정리하지 못할 수 있습니다. 이때 HA의 해당 MQTT 엔티티/기기 제거 또는 해당 discovery config topic에 빈 retained 메시지 발행이 필요합니다.
- 전력 측정값은 표준 powerMeter/energyMeter/voltageMeasurement/currentMeasurement capability가 있는 기기만 가능하며 원본 단위가 지원되어야 합니다. 고유 custom capability 및 특수 제조사 기능은 기존 SmartThings 앱에서 계속 사용합니다.
- 코드, 모델 매핑 단위 테스트와 패키지 생성 검증은 실제 삼성 허브 SDK/CLI 업로드/기기 동작 검증을 대체하지 않습니다. 0.1.0은 개발 후보이며 실기 검증 전 기존 시스템을 유지하세요.

## 라이선스

원본 MIT 라이선스는 생성 패키지에 LICENSE.upstream으로 포함합니다. 원본 프로젝트 및 Zigbee2MQTT/zigbee-herdsman-converters의 기여를 명시합니다. 신규 MQTT 모듈은 ST 프로젝트에서 관리합니다.
