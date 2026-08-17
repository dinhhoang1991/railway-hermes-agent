import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'iot-http-tool'
export const inject = ['tools']

const sensorCache: Record<string, any> = {}

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'http_update_sensor_data',
    description: 'Cập nhật dữ liệu cảm biến IoT vào bộ nhớ cache (HTTP). Dùng khi chưa có nguồn MQTT để nạp thủ công giá trị cảm biến.',
    parameters: {
      sensor_id: { type: 'string', required: true, description: 'ID cảm biến' },
      value: { type: 'number', required: true, description: 'Giá trị đo được' },
      type: { type: 'string', required: false, description: 'Loại cảm biến (tilt, vibration, water...)' },
      unit: { type: 'string', required: false, description: 'Đơn vị' },
      extra: { type: 'string', required: false, description: 'Thông tin thêm (chuỗi JSON hợp lệ)' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      let extra = {}
      if (args.extra) {
        try {
          extra = JSON.parse(args.extra)
        } catch {
          return 'Lỗi: tham số `extra` không phải chuỗi JSON hợp lệ'
        }
      }

      sensorCache[args.sensor_id] = {
        sensor_id: args.sensor_id,
        value: args.value,
        type: args.type || 'unknown',
        unit: args.unit || '',
        extra,
        updated_at: new Date().toISOString(),
      }
      return `Đã cập nhật cảm biến ${args.sensor_id}: ${args.value}`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'http_get_sensor_data',
    description: 'Lấy dữ liệu mới nhất của cảm biến IoT từ bộ nhớ cache (HTTP)',
    parameters: {
      sensor_id: { type: 'string', required: true, description: 'ID cảm biến, ví dụ cam-ranh-01' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const data = sensorCache[args.sensor_id]
      if (!data) {
        return `Không có dữ liệu của cảm biến ${args.sensor_id} trong cache`
      }
      return JSON.stringify(data, null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'http_list_sensors',
    description: 'Liệt kê tất cả cảm biến đang có dữ liệu trong bộ nhớ cache (HTTP)',
    parameters: {},
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute() {
      const keys = Object.keys(sensorCache)
      if (keys.length === 0) return 'Chưa có cảm biến nào trong cache'
      return keys.map(k => `${k}: ${JSON.stringify(sensorCache[k])}`).join('\n\n')
    },
  }))
}
