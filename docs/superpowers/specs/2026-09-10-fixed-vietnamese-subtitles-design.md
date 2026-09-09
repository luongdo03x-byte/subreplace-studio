# Phase 1 — Phụ đề Việt xếp dưới phụ đề gốc

Ngày: 2026-09-10. Trạng thái: thiết kế trong hội thoại đã được đồng ý; chờ duyệt bản tài liệu trước khi lập kế hoạch triển khai.

Nguồn yêu cầu: `/home/dluowng/Downloads/PTYC-Nang-cap-Module-Long-tieng.md` và brief phase 1 trong hội thoại. Các quyết định trong hội thoại ưu tiên hơn lộ trình cũ trong PTYC.

## 1. Phạm vi và quyết định đã thống nhất

- Phase 1 làm module ghi phụ đề Việt xuống dưới phụ đề Trung cứng. Không mở rộng chức năng lồng tiếng trong phase này.
- Giữ luồng tạo/dịch nhiều video và gộp theo thứ tự hiện tại. Nhận bản dịch từ pipeline đang có, đồng thời hỗ trợ video + phụ đề Việt có sẵn.
- Không xóa, làm mờ, che hoặc crop chữ Trung. Sai khác pixel do mã hóa mất dữ liệu CRF 18–20 được chấp nhận; tiêu chí giữ pixel áp dụng trước encoder, không phải so sánh bit-exact video nén đầu ra với đầu vào.
- Mỗi video nguồn có một Y riêng, cố định tuyệt đối trong nguồn đó. Y được phép khác khi chuyển nguồn trong video gộp.
- Khóa Y và chiều cao mở rộng; sửa tay áp dụng cho toàn nguồn và yêu cầu preview/duyệt lại.
- Dò thấy chồng chữ thì chặn nguồn đó, báo timestamp để người dùng chỉnh. Không tự thay Y theo câu, cảnh hoặc khung hình.
- Duyệt preview theo lô. Nguồn lỗi không chặn các nguồn khác tiếp tục phân tích/preview. Chỉ gộp khi tất cả nguồn trong danh sách gộp đã được duyệt và render thành công.

## 2. Hiện trạng và điểm tích hợp

Repo thiết kế: `/home/dluowng/subreplace-studio`.

- `app/core/rendering/ass.py` đã có BELOW_ANCHOR và neo trên, nhưng dùng median anchor, chưa phải P95 mép dưới khối chữ.
- `app/core/rendering/placement.py` có logic đẩy Y lên để vừa khung; không dùng logic này cho chế độ mới.
- `app/application/batch.py` chạy các nguồn tuần tự, hỗ trợ giữ output khi retry. Cần bổ sung pha chuẩn bị/duyệt, sau đó render/gộp.
- `app/core/media/ffmpeg.py::concat` hiện mã hóa chuẩn hóa từng đoạn rồi nối; luồng mới phải chuẩn hóa ngay khi render lần đầu.
- Project hiện lưu JSON. Module mới dùng SQLite làm nguồn trạng thái chính cho layout, revision, duyệt và batch manifest; JSON chỉ giữ liên kết/khả năng mở project cũ.
- Shortcut desktop đang dùng gói cài 0.3.0 trong môi trường Python ở ổ ngoài, không trực tiếp chạy repo. Cập nhật bản cài là bước riêng sau triển khai và kiểm thử; không sửa nhầm `subreplace-studio-next`, nơi đang có thay đổi chưa commit.

## 3. Thành phần và luồng dữ liệu

Các thành phần có trách nhiệm riêng:

1. Bộ chuẩn bị phụ đề: nhập text/timestamp hoặc nhận bản dịch hiện có, tạo DisplaySegment độc lập với segment lồng tiếng.
2. Bộ dò dải chữ: lấy mẫu, gom khối nhiều dòng, tính P95 và báo chất lượng dò.
3. Bộ lập layout: đo font thực, tính Y/H và kiểm tra đủ chỗ.
4. Kho SQLite: lưu revision, layout, duyệt, trạng thái từng nguồn và thứ tự batch.
5. Bộ kiểm tra va chạm: kiểm tra toàn nguồn với layout đã khóa, trả timestamp; không cập nhật Y.
6. Bộ preview/render: dùng chung ASS, font và cấu hình canvas/encoder.
7. Điều phối batch: chuẩn bị các nguồn, chờ duyệt, render từng nguồn, xác minh tương thích rồi nối.

Luồng: chọn nhiều nguồn → dịch hoặc nhập phụ đề → dò và lập layout từng nguồn → xác định canvas chung nếu gộp → kiểm tra/5 PNG mỗi nguồn → duyệt theo lô → render các nguồn hợp lệ → nối theo thứ tự.

Tác vụ chạy nền, có tiến độ và hủy. Không yêu cầu người dùng chuyển sang công cụ khác hoặc nhập lại từng file khi dùng pipeline dịch hiện tại.

## 4. Thuật toán dò và khóa

1. Chọn 300 thời điểm rải đều toàn thời lượng, giải mã khung tương ứng. Video có dưới 300 khung dùng các khung duy nhất hiện có, không nhân bản để tăng độ tin cậy; ghi cảnh báo thiếu mẫu.
2. Chạy bộ dò chữ trên nửa dưới. Quy đổi hộp về hệ tọa độ toàn khung nguồn đã xét rotation metadata.
3. Gom các hộp thành dòng và khối phụ đề; xử lý cả hai dòng Trung và khối Trung–Anh. Lọc dải thuộc 40% đáy, lệch tâm ngang <15% chiều rộng và hiện diện trong ≥20% khung mẫu. Tần suất tính theo dải vị trí, mỗi khung tối đa một lần cho một dải; không yêu cầu cùng text hoặc tọa độ hộp giống hệt.
4. `y_cam` là P95 mép dưới các khối hợp lệ, dùng nội suy tuyến tính; không thay bằng max. Ngưỡng gom dải phải là cấu hình thuật toán có phiên bản và được kiểm chứng bằng video mẫu.
5. `y_da_khoa = ceil(y_cam + 0.008 * source_height)`.
6. `chieu_cao_can = 2 * chieu_cao_dong + le_duoi`. Đo line box/font thực, bao gồm khoảng cho dấu, viền và bóng. Lề dưới mặc định đề xuất là `ceil(0.02 * source_height)`.
7. `chieu_cao_dai_them = max(0, ceil(y_da_khoa + chieu_cao_can - source_height))`.
8. Lưu và khóa cặp giá trị vào SQLite theo revision trước khi render. Render chỉ đọc; không tự dò hoặc tính lại cặp này.

Nếu không có dải hợp lệ, dùng mặc định đề xuất: Y bằng `ceil(0.90*h)` cho ngang/vuông, `ceil(0.88*h)` cho dọc; vẫn tính phần mở rộng, lưu khóa và bật cờ fallback. Đây là vị trí chưa được bộ dò xác nhận an toàn, phải hiện rõ khi duyệt.

Mất khung/giải mã lỗi phải ghi cảnh báo và số mẫu thực tế. Không âm thầm coi thiếu dữ liệu là dò thành công. Tỷ lệ hiện diện tính trên số khung mẫu giải mã được; metadata ghi riêng số mẫu yêu cầu, số giải mã được và số có dải hợp lệ.

## 5. Chữ, ASS và phân đoạn hiển thị

- Mặc định đề xuất Be Vietnam Pro, cỡ 48; style cho phép cấu hình font, cỡ, màu, viền/bóng. Kiểm tra file font, glyph tiếng Việt và giấy phép trước khi đóng gói; không âm thầm thay font khi render.
- Đo độ rộng bằng font thực; ngắt ở ranh giới từ, chọn điểm chia cân chiều rộng. ASS dùng Format chuẩn đầy đủ, `Alignment: 8`, MarginV bằng Y đã khóa, WrapStyle 2 và PlayRes khớp canvas xuất.
- Không nhận override vị trí/font tùy ý từ ASS đầu vào: lấy text/timestamp và tạo ASS mới theo style đã duyệt.
- Giữ cỡ chữ đã duyệt cho nguồn, không thu nhỏ theo từng câu. Line box dòng đầu có cùng tọa độ cho câu một và hai dòng. Không định nghĩa Y theo pixel mực cao nhất của từng glyph vì hình dạng dấu khác nhau.
- Câu không vừa hai dòng được tách thành DisplaySegment liên tiếp trong khoảng thời gian cue gốc, giữ thứ tự và toàn bộ text. Thời gian phân bổ theo lượng text; không tự gộp theo segment lồng tiếng.
- Ngưỡng cảnh báo đề xuất: phân đoạn dưới 800 ms hoặc quá 20 ký tự/giây. Câu không thể chia theo ranh giới từ, cue chồng thời gian hoặc tràn chiều rộng phải báo sửa, không cắt chữ hoặc để ASS tự xếp thêm hàng.
- Kiểm thử trực tiếp `ệ ợ ữ ậ ỗ ằ`, cả Unicode dựng sẵn và tổ hợp sau chuẩn hóa NFC, một/hai dòng, sát mép dưới và có outline/shadow.

## 6. Kiểm tra toàn nguồn và preview

Sau khi layout/canvas được xác định, chạy kiểm tra chữ trên toàn bộ các khung của nguồn, có thể dùng cache dò hiện có nếu bao phủ đủ. So hộp chữ gốc với vùng chiếm chỗ phụ đề Việt tại thời điểm có cue, bao gồm viền/bóng. Kết quả chỉ là báo cáo, không điều chỉnh Y.

Nếu phát hiện chồng, lưu timestamp/hộp và chặn xuất nguồn; người dùng chỉnh Y cho toàn nguồn, tính lại H trong một revision mới, kiểm tra và duyệt lại. Lỗi bộ dò/giải mã khiến kiểm tra không hoàn tất cũng chặn xuất. Bộ dò có thể bỏ sót chữ: kiểm tra này không chứng minh bảo đảm tuyệt đối mọi pixel; nghiệm thu cần đối chiếu thực tế trên bộ video có nhãn.

Xuất đúng 5 PNG phân bố trên thời lượng, dùng cùng renderer/font/canvas/ASS với bản cuối. Chọn thời điểm có cue trong năm khoảng thời gian; nếu khoảng không có cue, dùng câu mẫu có nhãn rõ trong giao diện để kiểm tra bố cục, không thêm câu mẫu vào video thật. Kèm timestamp và phân biệt ảnh dùng text thật/câu mẫu.

Người dùng duyệt một hoặc nhiều nguồn trong danh sách. Nguồn có cảnh báo chặn không được duyệt bằng thao tác duyệt cả lô. Fallback phải được thông báo và xác nhận rõ; không mô tả nó như kết quả dò thành công.

## 7. Khung chung và gộp một lần mã hóa

Khi gộp, xác định canvas trước preview cuối cùng:

- W chung là chiều rộng lớn nhất; H chung là lớn nhất của `(source_height + chieu_cao_dai_them)`; làm tròn lên kích thước chẵn khi profile encoder yêu cầu.
- Giữ ảnh nguồn ở mép trên, căn giữa ngang, chỉ thêm đệm hai bên/đáy. Không scale/crop hình gốc trong chế độ này. Y vẫn tính từ mép trên nên không thay đổi.
- Phân biệt H mở rộng cần cho phụ đề của từng nguồn với phần đệm bổ sung cho canvas chung và làm tròn encoder. Lưu tất cả vào render profile; không ghi đè H nguồn bằng H batch.
- Pixel aspect ratio/rotation phải được kiểm tra trước khi chọn profile. Phase 1 chặn trường hợp SAR khác 1 nếu chưa có đường xử lý bảo toàn hình đã kiểm chứng, thay vì tự scale làm thay đổi chữ.
- Chốt chung codec/profile/pixel format, FPS/time base và audio profile; mặc định đề xuất FPS theo nguồn đầu. Khác FPS được chuẩn hóa trong lần render đầu, giữ timeline âm thanh; preview hiển thị thông số đầu ra.
- Nguồn không có audio được bổ sung silence nếu batch cần track audio thống nhất. Audio batch chuẩn hóa AAC 48 kHz stereo; xuất riêng có thể copy audio tương thích.
- Render trực tiếp từ nguồn gốc: pad + ASS + audio hiện có trong một lần mã hóa video libx264 CRF 18, preset medium. Kiến trúc cho phép nối audio lồng tiếng vào cùng lệnh sau này.
- Trước concat kiểm tra tương thích stream và thời lượng. Nối bằng stream copy; nếu không tương thích thì báo lỗi profile, không tự chạy thêm một vòng mã hóa video.

Thay thành phần batch có thể đổi canvas chung và làm mất hiệu lực preview/output liên quan. Retry với cùng profile/revision phải tái sử dụng nguồn hoàn thành; không chỉ kiểm tra file tồn tại và khác 0 byte.

## 8. Dữ liệu, khôi phục và đầu ra

SQLite lưu theo source/project ID: fingerprint video và phụ đề, style/font fingerprint, detector version, Y/H tự động và hiệu lực, cờ chỉnh tay, fallback, số mẫu, cảnh báo, layout revision, render profile, preview paths, collision report, approved revision, trạng thái render/output. Batch manifest lưu danh sách có thứ tự và profile chung.

Các thay đổi video/phụ đề/style/font/Y/canvas làm mất duyệt và các artifact phụ thuộc. Điều chỉnh tay tạo revision mới trước kiểm tra/preview; không sửa revision đang render. Thay text không bắt buộc dò lại nguồn nếu fingerprint video và detector còn nguyên.

Đầu ra mỗi nguồn gồm video, ASS/SRT theo tùy chọn xuất và metadata tối thiểu:

```json
{
  "y_da_khoa": 900,
  "chieu_cao_dai_them": 40,
  "che_do": "mo_rong_khung",
  "dung_gia_tri_mac_dinh": false,
  "so_khung_mau_do_duoc": 250,
  "canh_bao": []
}
```

Các số trên minh họa schema. `so_khung_mau_do_duoc` đếm khung có khối thuộc dải phụ đề đã lọc, không phải số hộp. `che_do` dựa trên H cần của nguồn; thông tin canvas/đệm batch nằm trong metadata bổ sung.

Trạng thái logic: chuẩn bị → chờ duyệt hoặc cần sửa → đã duyệt → đang render → hoàn thành/lỗi. Dừng hoặc lỗi giữ DB/preview và kết quả hợp lệ để tiếp tục. Ghi output tạm rồi xác minh trước khi công bố; giữ dữ liệu cần retry khi dọn cache. Không để cleanup_project hiện tại xóa trạng thái nguồn đang chờ duyệt hoặc lỗi.

## 9. Kiểm chứng và nghiệm thu

- Unit: gom khối nhiều dòng, tần suất theo khung/dải, P95 chống outlier, làm tròn Y/H, fallback, cặp khóa bất biến và invalidation revision.
- Renderer: một/hai dòng cùng top line box, tối đa hai dòng, không cắt text/dấu, không tự dịch Y do cue trùng thời gian, preview khớp cấu hình bản cuối.
- Trước encoder: vùng pixel chữ gốc không bị filter ghép hình tác động; không dùng phép so bit-exact sau CRF 18 để đánh trượt tiêu chí này.
- Integration: batch nguồn khác chiều cao mở rộng, khác FPS, nguồn không audio, duyệt theo lô, sửa tay, restart/retry, nguồn lỗi không bị âm thầm bỏ khỏi bản gộp, thứ tự đúng và chỉ một lần mã hóa hình.
- Dùng 10 video có phụ đề ở nhiều vị trí, ít nhất hai sát đáy và hai có hai dòng; thêm tình huống Trung–Anh, không hardsub và phụ đề thấp hiếm gặp.
- Ngưỡng: Y lệch 0 pixel trong từng nguồn; 0 cảnh chồng chữ trong bộ nghiệm thu; 0 cắt dấu; 0 cue quá hai dòng; 0 thao tác xóa/làm mờ/che chữ gốc; tự dò đúng không chỉnh tay ít nhất 9/10 video.
- Đánh giá dò tự động trước chỉnh tay để không làm đẹp tỷ lệ. Quét toàn khung có chi phí đáng kể; đo thời gian trên máy thực tế, chưa cam kết tốc độ từ tài liệu lồng tiếng cũ.

## 10. Ranh giới triển khai

Tài liệu này chưa triển khai code và chưa cập nhật app cài đặt. Sau khi người dùng duyệt bản tài liệu, lập kế hoạch triển khai theo skill writing-plans. Các giá trị ghi là mặc định đề xuất là lựa chọn cụ thể của bản thiết kế để người dùng review, không phải tham số đã được đo tối ưu trên 10 video thực tế.
