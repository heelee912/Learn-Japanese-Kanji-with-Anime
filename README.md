개인적으로 학습에 가장 동기 부여가 되는 것은 재미라고 생각합니다.

따라서 별도로 공부하는 것보다 비록 시간은 오래 걸릴 수 있지만, 오히려 그 오래 지속할 수 있는 자신만의 학습법을 찾는 것이 중요하다고 생각합니다.

원래는 반복을 통해 시청의 흐름을 끊는 것도 그렇게 선호하지 않지만, 한 번 보는 것과 반복하는 것의 차이는 크기 때문에 그나마 가장 기존 방식에서 벗어나지 않고 최대한 원하는 대로 커스터마이징 할 수 있게 한 프로젝트입니다.

애니메이션을 오래 봐서 듣는 것에는 큰 무리가 없지만 한자를 잘 모르는 사람에게 효과가 가장 좋을 것이라고 생각합니다.


---


일본어 자막과 한국어 자막을 원하는 폰트 크기대로 지정해서 자연스럽게 합칠 수 있는 ass batch.py 와,

mpv 플레이어에서 동작하는 repeat_jp_cluster.lua가 포함된 프로젝트입니다.

유용한 링크 :

https://jimaku.cc/

를 통해 일본어 자막을 받을 수 있습니다.


---


1. 싱크 조절

스폰서 싱크 조절은 말 그대로 자막의 싱크를 조절하는 기능입니다

자막 파일과 같은 경로에 두고 실행 시 전체 싱크 및 특정 문구 부터의 싱크를 개별적으로 지정할 수 있습니다.
타임라인에 직접 더하거나 빼지는 값으로, 예를 들어 음수의 경우 자막의 타임라인을 그만큼 빠르게 합니다.

전체 프로젝트와는 상관이 없지만 먼저 싱크가 맞는 한글 및 일본어 자막을 준비하기 전 단계입니다.

<img width="244" height="53" alt="image" src="https://github.com/user-attachments/assets/ffc48668-27e9-4a7b-9d56-e80f6d714ab5" />

---


2. 자막 병합

싱크가 맞는 한글 일본 자막 파일을 각각 만들었다면, 자막을 병합할 차례입니다.

<img width="352" height="166" alt="image" src="https://github.com/user-attachments/assets/911ed986-417b-4ac9-892d-4a3f1dc5229e" />

ass batch를 실행한 후,

영상 -> 한글자막 -> 일본자막 순으로 선택해줍니다.

선택 후 폰트 사이즈를 설정하면 자동으로 영상 바로 옆에 동일 파일의 통합 ass파일을 생성하여 줍니다.

참고로 기본값인 25, 120의 경우 아래와 같습니다.

<img width="693" height="233" alt="image" src="https://github.com/user-attachments/assets/9bdbe1bc-7dff-4bd3-b5d1-c093573ab56f" />

참고로 폰트의 경우

<img width="199" height="38" alt="image" src="https://github.com/user-attachments/assets/07b79773-9203-4e20-bb02-401d01360326" />

해당 내용을 수정하여 폰트를 지정 가능합니다. 다만 실제 지원되는 폰트는 플레이어 환경 및 세팅에 따라 다릅니다

---

3. 일본어 자막 위치 반복재생

이 번호의 가이드는 mpv-android를 기준으로 합니다.

repeat_jp_cluster.lua 를 다운받고, 

/storage/emulated/0/Android/media/is.xyz.mpv/scripts/repeat_jp_cluster.lua
가 되도록 넣어줍니다.

잘 모르겠다면
기본 내장메모리/Android/media/is.xyz.mpv/scripts
폴더에 넣어줍니다.

이후 mpv-androud 어플 settings -> Advaced -> Edit mpv.conf 를 선택하여

script=/storage/emulated/0/Android/media/is.xyz.mpv/scripts/repeat_jp_cluster.lua

를 입력해 줍니다.

<img width="644" height="360" alt="image" src="https://github.com/user-attachments/assets/bab74c45-cca0-4b3a-ac6a-2e9dadb3b419" />

클러스터 : 

<img width="1230" height="219" alt="image" src="https://github.com/user-attachments/assets/3b9c45e2-acb7-482c-97d2-c0c325eac24d" />
병합 자막 파일은 개인적인 선호에 따라 본래 자막을 따로따로 타임라인을 나눠 병합됩니다.
이렇게 할 경우 일본어 자막 밑에 한글 자막의 라인수가 변하더라도 자연스럽게 글자 크기만 다른 글처럼 실시간으로 바닥에 붙게 나오게 됩니다.

이 경우 일본어 자막만을 보기 위해 {!JP} 태그를 통해 lua에서 구분하게 됩니다.
여러 다이얼로그가 달라붙어있는 동일 문자열으로 하나로 파악되는 경우 클러스터가 됩니다.

즉, 한마디로 대사의 길이와 자막의 글자수를 통해 반복 여부를 결정하고, 반복 횟수도 결정 가능합니다.
(반복 횟수의 경우 재생 후 반복하는 횟수. 따라서 총 재생수는 N+1)

local DEBUG 같은 경우 디버깅용 코드로 화면에 뜰 경우 false로 할 수 있습니다.

반복 후 넘어가쓴데 뒤로 돌려 다시 반복하고 싶을 경우를 위해,
뒤로 감기 조건 및 finished 플래그 삭제 시간을 두었습니다.

기본적으로 대사 길이, 글자수, 반복 횟수를 제외하고는 기본값으로 두어도 된다고 생각합니다.


사실 루프 방식이 한정된 로컬 재생이라면 더 효율적인 방법이 있긴 한데, 항상 보장되는 환경은 아니니 이 정도도 괜찮은 것 같습니다.

참고로, 로컬이 아닌 서버에 접속해서 플레이하는 경우
조합하는 파일탐색기에 따라서 자막을 안 보내주는 FTP지원 파일탐색기도 있으니, 개인적으로는 젤리핀+외부플레이어 mpv 조합을 추천하지만 CX파일탐색기도 자막을 넘겨주는 파일탐색기입니다.

---

4. 기타 유용한 mpv.conf

sub-ass-force-style=ScaleX=1.2,ScaleY=1.3

- ass 자막의 가로 및 세로 배율 조정이 가능합니다. (MX 플레이어의 배율보다 더 고급 기능)

sub-ass-force-margins=yes
sub-use-margins=yes

- ass 자막도 영상 외 레터박스 영역에 둘 수 있도록 합니다.


0x10001 add sub-delay -0.5
0x10003 add sub-delay 0.5

- mpv.conf 가 아닌 input.conf에 넣어야 합니다. 단순히 전체 자막 싱크를 좌측 두 번 터치로 자막 타임라인 0.5초 감소(빠르게), 우측 두 번 터치로 자막 타임라인 0.5초 증가(느리게)가 가능합니다. 이미 싱크를 앞에서 맞추었지만 추가적으로 맞추고 싶은 경우 사용할 수 있습니다.




