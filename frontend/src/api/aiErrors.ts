import { isAxiosError } from 'axios';
import { SESSION_EXPIRED_MESSAGE } from '../types/ai';

export const SERVICE_UNREACHABLE_MESSAGE = 'Không thể kết nối hệ thống HR. Vui lòng kiểm tra kết nối và thử lại. Báo cáo và dữ liệu cá nhân cần kết nối hệ thống.';

/** Read JSON errors even when a PDF/XLSX request used responseType: blob. */
export async function aiErrorMessage(error: unknown, fallback: string): Promise<string> {
  if (!isAxiosError(error)) return fallback;
  if (!error.response) return SERVICE_UNREACHABLE_MESSAGE;
  let data: unknown = error.response.data;
  if (data instanceof Blob && data.size <= 65536) {
    try { data = JSON.parse(await data.text()); } catch { data = null; }
  }
  if (data instanceof ArrayBuffer && data.byteLength <= 65536) {
    try { data = JSON.parse(new TextDecoder().decode(data)); } catch { data = null; }
  }
  if (data && typeof data === 'object' && 'message' in data && typeof data.message === 'string' && data.message.length <= 2000) return data.message;
  if (error.response.status === 401) return SESSION_EXPIRED_MESSAGE;
  if (error.response.status === 403) return 'Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.';
  if (error.response.status === 410) return 'File báo cáo đã hết hạn. Vui lòng tạo báo cáo mới.';
  if (error.response.status === 422) return 'Thông tin chưa hợp lệ. Vui lòng kiểm tra các trường được yêu cầu.';
  if (error.response.status === 429) return 'Bạn đang gửi yêu cầu quá nhanh. Vui lòng thử lại sau.';
  if (error.response.status >= 500) return 'Hiện không thể truy xuất dữ liệu HR. Vui lòng thử lại sau. Báo cáo chưa được tạo.';
  return fallback;
}
