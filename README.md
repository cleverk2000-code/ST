# ST Local Bridge v0.1.0 (실험판)

삼성 SmartThings 허브에 이미 등록된 Zigbee 기기를 유지하고 HA의 MQTT로 로컬 제어/상태 보고를 연결합니다. 삼성 TV 내장 허브를 목표로 하지만 실제 S85F 호환성은 아직 검증하지 않았습니다. SmartThings 공식 통합과 별개이며 PSK, 허브 IP 직접 접속, 상시 Cloud API 토큰은 필요하지 않습니다.

## 구성

HA MQTT → Edge MQTT 버튼 → SmartThings Local Rule → 실제 Zigbee 스위치
실제 기기 상태 → 별도 Local Rule → MQTT Creator publish → HA

ON/OFF마다 별도의 순간 버튼을 사용해 가상 스위치 상태 불일치 문제를 피합니다. 반복 pushed 이벤트가 실제 허브에서 트리거되는지 확인해야 합니다. HA는 명령을 상태로 간주하지 않습니다. 명령은 QoS 1, retain false. 상태는 실제 보고만 반영합니다. 재시작 후에는 상태 보고 전까지 unknown일 수 있고, 허브가 끊겨도 마지막 상태가 남을 수 있습니다(허브 heartbeat/availability는 미구현).

## 1. 사전 준비

- HA Mosquitto broker 및 MQTT 통합 정상 연결. 브로커 주소는 **HA VM의 내부 IP**이며 TV IP와 다릅니다. 인증 계정 사용, 외부 포트 개방 금지.
- [TAustin MQTTDevices](https://github.com/toddaustin07/MQTTDevices) README의 채널 초대 링크에서 TV 허브를 선택하여 MQTT Devices V1.7 설치. SmartThings 앱에서 주변 검색으로 MQTT Device Creator 생성, 브로커 IP와 계정 입력. Connected 확인.
- SmartThings Advanced에서 실제 기기 UUID, Creator UUID, Location UUID 확인. 같은 허브에 연결된 로컬 실행 가능한 기기만 사용.

## 2. 스위치용 Edge 버튼 설정

실제 기기 UUID를 D라고 할 때 Creator에서 MQTT Button 두 개 생성합니다.

| 설정 | ON 버튼 | OFF 버튼 |
| --- | --- | --- |
| Subscribe Topic | st/local/D/on | st/local/D/off |
| Expected Message format | string | string |
| PRESSED 값 | pushed | pushed |
| Publish state changes | OFF | OFF |

D는 실제 UUID(소문자 하이픈 형식)로 치환합니다. 버튼 둘의 UUID도 기록합니다. Subscribed 확인. 다른 기기마다 버튼 두 개를 별도로 만듭니다. 센서의 경우 버튼은 필요 없습니다.

## 3. Rules 생성

Python 3.11+가 있는 PC 또는 HA 터미널에서 이 저장소를 내려받습니다. 라이브러리 설치 불필요. 예시 UUID를 실제 값으로 대체합니다.

    python3 tools/st_rules.py --device D --creator C --on-button A --off-button B

위 명령은 JSON을 출력할 뿐 SmartThings를 변경하지 않습니다. 스위치용 4개 Rule (ON/OFF 명령, ON/OFF 상태 보고)을 각각 생성합니다. 센서는 --kind motion/contact/moisture/presence 중 하나로 지정하고 버튼 인수를 생략합니다. main 컴포넌트만 지원합니다.

선택 사항: SmartThings의 초기 설정 API를 쓰려면 토큰을 환경변수 ST_TOKEN에 설정하세요(저장소나 채팅에 넣지 마세요). 읽기 기기/위치 및 Rules 읽기/쓰기 권한이 필요하며 PAT는 보통 24시간 유효합니다. 실행 시 명령줄에 직접 토큰을 넣지 않습니다.

    python3 tools/st_rules.py --list --location L
    python3 tools/st_rules.py --device D --creator C --on-button A --off-button B --location L --apply

--apply는 실제 Rule을 생성합니다. 동일 이름 Rule이 있으면 사전에 중단합니다. 생성 뒤 executionLocation이 Local이 아니거나 확인되지 않으면 중단하고 이미 생성한 ID를 출력합니다. 부분 실패 시 해당 ID들을 Advanced/API에서 직접 확인하고 필요하면 삭제하십시오. 로컬 여부가 검증되지 않은 Rule은 사용하지 마세요. 토큰은 설정 시에만 사용합니다. 가상 버튼 생성/설정은 현재 수동입니다.

## 4. HA 등록 (HACS)

HACS → 우측 ⋮ → 사용자 지정 저장소 → https://github.com/cleverk2000-code/ST → Integration → ST Local Bridge 다운로드. HA 재시작 후 설정 → 기기 및 서비스 → 통합 추가 → ST Local Bridge → 실제 기기 UUID, 표시 이름, 종류 입력. 실제 스위치/조명은 switch 엔티티로 등록되며 센서는 binary_sensor로 등록됩니다. 기기마다 반복합니다. HACS가 아직 실험판을 설치하지 못한다면 custom_components/st_local_bridge 폴더를 HA /config/custom_components/에 복사하고 재시작하세요.

## 5. 검증 (처음에는 위험하지 않은 조명 하나)

1. MQTT 설정 화면에서 st/local/D/# 토픽 수신 대기.
2. 물리 조명 ON/OFF → /state on/off 수신 및 HA 상태 갱신 확인.
3. HA ON/OFF → /on 또는 /off pushed 전송 → 실제 기기 작동 → /state 수신 확인.
4. 물리 스위치와 HA를 번갈아 사용하고 동일 명령 반복 시에도 작동하는지 확인.
5. TV 대기 상태, HA/MQTT 재시작, 허브 재시작 후 재확인. 초기 상태는 실제 상태 변경으로 보고를 발생시키십시오.
6. 안전한 환경에서 WAN만 차단(LAN/Wi-Fi 유지) 후 제어 및 상태 보고 양방향 확인. 실패하면 공식 클라우드 통합을 유지하세요.

기존 클라우드 통합을 제거하지 말고 테스트용 새 엔티티에서 먼저 검증하세요. 잠금장치/가스/난방 등 안전 관련 기기는 현재 지원하지 않습니다. 자동 기기 가져오기, 밝기/색상/수치 센서, 상태 초기 조회, 허브 연결 감시는 아직 미구현입니다.

## 참고
- https://github.com/toddaustin07/MQTTDevices (외부 Edge 드라이버, 이 저장소에서 재배포하지 않음)
- https://developer.smartthings.com/docs/automations/rules
- https://www.home-assistant.io/integrations/mqtt/

