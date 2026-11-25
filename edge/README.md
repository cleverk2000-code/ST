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
6. 기존 HA ST Local Bridge 통합에 실제 UUID를 등록합니다. 스위치 명령 토픽은 /on 및 /off, payload pushed. 상태는 /state on/off. /availability 및 /heartbeat는 HA 통합에서 전용 Edge 옵션을 선택하면 자동 감시합니다.
7. 다음 기기 추가 시 현재 프록시에 UUID를 입력한 뒤 다시 주변 검색. 중복 물리 UUID 설정 금지. 기존 TAustin 토픽과 같은 UUID로 동시에 연결하지 마세요.
8. 브로커 재시작, 인터넷 차단(LAN 유지), TV 대기 상태, 동일 ON 반복, HA/허브 재시작 시험. 위험하지 않은 조명 하나만 사용. 기존 클라우드 통합 유지.

## 현재 한계

- MQTT 3.1.1, 인증된 사설 IPv4 TCP, QoS1 명령 수신/ACK, QoS0 상태 보고, retained 명령 거부, clean session, PINGRESP 감시, 1~30초 재연결 backoff, retained availability/Last Will 및 15초 heartbeat.
- 상태는 세션 시작 시 이전 retained 값을 지우고 실제 보고를 기다립니다. 연결이 끊긴 동안 명령은 재생하지 않습니다. QoS1 중복 명령은 가능하므로 실제 동작은 절대 ON/OFF만 사용.
- MQTT Discovery 및 물리 기기 일괄 자동 생성은 후속 구현. TLS 미지원. 프록시 1개당 연결 1개.
- 실제 TV 허브 SDK, 패키징, 설치 및 Rules 실행은 아직 실기 검증되지 않았습니다. CLI 계정 인증은 사용자가 직접 수행해야 합니다.

## Edge v0.2.1 hotfix

TV 허브에서 MQTT 인증 직후 연결 종료가 반복되는 현상을 대응합니다. 0초 timeout bulk receive를 제거하고 1바이트 cosock 수신, timeout/partial 처리, send 반환값 호환, 단계별 안전한 오류 로그를 추가했습니다. 원인 확정 및 실기 재검증은 아직 필요합니다. 같은 packageKey로 다시 package → assign → install 하세요. 기존 설정은 유지될 것으로 예상되나 설치 후 확인하세요.

## v0.3.0: 창문 브리지

기존 bridge 프로필 및 기기 설정은 그대로 유지합니다. 창문은 새 bridge-v3 프로필의 프록시가 필요합니다. 기존 창문용 ST Local Edge 1의 Enable bridge를 OFF한 뒤 드라이버를 업데이트하고 주변 검색하여 새 ST Local Edge 기기를 만드세요. 실제 창문을 삭제하지 마세요. 새 프록시 설정에 동일한 실제 UUID와 MQTT 접속 정보, Window cover mode=ON, Enable bridge=ON을 지정합니다. 동일 UUID를 사용하는 이전 프록시는 OFF 상태를 유지합니다.

HA HACS 통합도 0.3.0으로 갱신 후 재시작하고 종류 cover로 등록합니다. 예전 등록이 있으면 삭제 후 새 종류로 추가해야 합니다(기존 공식 SmartThings 통합은 유지). MQTT 상태 토픽 /shade, 명령 /on /off /stop, payload pushed. 상태는 실제 windowShade 보고를 사용합니다. 백분율 위치와 배터리 동기화는 아직 구현되지 않았습니다. 정지는 실제 기기가 pause를 지원하는지 검증하세요.

    python tools/edge_rules.py --device PHYSICAL_UUID --proxy NEW_PROXY_UUID --kind cover

출력된 10개 Rules를 개별 설치(또는 앱의 해당 조건/동작으로 생성)하고 각각 로컬 실행 확인. 기존 물리 창문 스케줄은 테스트 중 일시 정지하고 수동으로 안전한 환경에서 확인하세요. 창문 움직임을 직접 볼 수 있는 상태에서만 첫 제어 테스트를 진행하세요. 위치 조회 및 명령은 추후 지원. 브리지 초기화 시 상태는 실제 보고 전까지 unknown입니다.
