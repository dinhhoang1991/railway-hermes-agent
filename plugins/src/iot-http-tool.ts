import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'iot-http-tool'
export const inject = ['tools']

const sensorCache: Record<string, any> = {}

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'update_sensor_data',
    description: 'Cập nhật dữ liệu cảm biến IoT vào bộ nhớ cache',
    parameters: {
      sensor_id: { type: 'string', required: true, description: 'ID cảm biến' },
      value: { type: 'number', required: true, description: 'Giá trị đo được' },
      type: { type: 'string', required: false, description: 'Loại cảm biến (tilt, vibration, water...)' },
      unit: { type: 'string', required: false, description: 'Đơn vị' },
      extra: { type: 'string', required: false, description: 'Thông tin thêm (JSON string)' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      sensorCache[args.sensor_id] = {
        sensor_id: args.sensor_id,
        value: args.value,
        type: args.type || 'unknown',
        unit: args.unit || '',
        extra: args.extra ? JSON.parse(args.extra) : {},
        updated_at: new Date().toISOString(),
      }
      return `Đã cập nhật cảm biến ${args.sensor_id}: ${args.value}`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'get_sensor_data',
    description: 'Lấy dữ liệu mới nhất của cảm biến IoT',
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
        return `Không có dữ liệu của cảm biến ${args.sensor_id}`
      }
      return JSON.stringify(data, null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'list_sensors',
    description: 'Liệt kê tất cả cảm biến đang có dữ liệu',
    parameters: {},
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute() {
      const keys = Object.keys(sensorCache)
      if (keys.length === 0) return 'Chưa có cảm biến nào'
      return keys.map(k => `${k}: ${JSON.stringify(sensorCache[k])}`).join('\n\n')
    },
  }))
}
