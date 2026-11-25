# ST Local Edge v0.2.0 experimental

전용 Edge 드라이버 첫 실험 버전. 기존 Zigbee 드라이버는 건드리지 않습니다. 물리 기기마다 가상 프록시 하나를 만들며 최대 16개 슬롯. 물리 상태는 Rule이 프록시 main switch 명령으로 보고하고, MQTT 명령은 commandOn/commandOff 버튼 이벤트로만 변환합니다. 자동 Rules 생성은 JSON 출력까지 지원합니다.

## 설치

1. PC에 [SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli/releases)를 설치하고 삼성 계정으로 인증합니다.
2. 저장소를 clone 또는 ZIP 다운로드한 뒤 루트에서 다음을 실행합니다.

    smartthings edge:channels:create
    smartthings edge:drivers:package edge/st-local-edge
    smartthings edge:channels:assign
    smartthings edge:drivers:install

각 단계에서 자신의 채널, 방금 패키징한 ST Local Edge 드라이버와 TV 내장 허브를 선택합니다. CLI 프롬프트/버전에 따라 채널 enroll이 필요합니다. 공식 문서: https://developer.smartthings.com/docs/devices/hub-connected/driver-channels/

3. SmartThings 앱 주변 검색 → ST Local Edge 1 생성. 설정에 HA LAN IP(192.168.0.19), 포트 1883, MQTT 전용 계정, 실제 물리 기기 UUID 입력 후 Enable bridge 활성화. 비밀번호는 로컬 네트워크의 MQTT TCP에서 평문으로 전송되므로 신뢰할 수 있는 LAN에서만 사용하며 인터넷에 포트를 개방하지 않습니다.
4. HA MQTT 통합에서 st/local/실제UUID/# 구독. availability=online 및 15초 주기 heartbeat 확인. MQTT 세션만 검증한 것이며 물리 기기 상태/로컬 Rules 검증과는 다릅니다.
5. SmartThings Advanced에서 프록시 UUID 확인. 물리 기기 ID와 다릅니다. 다음 명령으로 Rules JSON 출력.

    python3 tools/edge_rules.py --device 실제UUID --proxy 프록시UUID

각 Rule을 SmartThings Rules API로 개별 등록하거나 SmartThings 앱에서 동일 루틴을 수동 구성하세요. commandOn 버튼 pushed → 물리 스위치 on; commandOff → 물리 스위치 off; 물리 스위치 on/off → 프록시 main switch on/off. 센서는 --kind motion/contact/moisture/presence 사용, 상태 보고 Rules만 생성됩니다. 모든 Rule의 executionLocation=Local 확인 필수. 초기 상태는 물리 기기의 실제 상태 변경 후 보고됩니다. 프록시 main 스위치는 상태 보고용이며 직접 앱에서 누르지 마세요.
6. 기존 HA ST Local Bridge 통합에 실제 UUID를 등록합니다. 스위치 명령 토픽은 /on 및 /off, payload pushed. 상태는 /state on/off. /availability 및 /heartbeat는 수동 관찰 가능하며 기존 HA 통합에는 아직 연결되지 않았습니다.
7. 다음 기기 추가 시 현재 프록시에 UUID를 입력한 뒤 다시 주변 검색. 중복 물리 UUID 설정 금지. 기존 TAustin 토픽과 같은 UUID로 동시에 연결하지 마세요.
8. 브로커 재시작, 인터넷 차단(LAN 유지), TV 대기 상태, 동일 ON 반복, HA/허브 재시작 시험. 위험하지 않은 조명 하나만 사용. 기존 클라우드 통합 유지.

## 현재 한계

- MQTT 3.1.1, 인증된 사설 IPv4 TCP, QoS1 명령 수신/ACK, QoS0 상태 보고, retained 명령 거부, clean session, PINGRESP 감시, 1~30초 재연결 backoff, retained availability/Last Will 및 15초 heartbeat.
- 상태는 세션 시작 시 이전 retained 값을 지우고 실제 보고를 기다립니다. 연결이 끊긴 동안 명령은 재생하지 않습니다. QoS1 중복 명령은 가능하므로 실제 동작은 절대 ON/OFF만 사용.
- MQTT Discovery 및 물리 기기 일괄 자동 생성은 후속 구현. TLS 미지원. 프록시 1개당 연결 1개.
- 실제 TV 허브 SDK, 패키징, 설치 및 Rules 실행은 아직 실기 검증되지 않았습니다. CLI 계정 인증은 사용자가 직접 수행해야 합니다.
