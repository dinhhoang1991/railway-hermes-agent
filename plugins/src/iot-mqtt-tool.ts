import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import mqtt from 'mqtt'

export const name = 'iot-mqtt-tool'
export const inject = ['tools']

const latestData: Record<string, any> = {}

export function apply(ctx: Context) {
  const brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://127.0.0.1:1883'

  const client = mqtt.connect(brokerUrl, {
    username: process.env.MQTT_USERNAME || undefined,
    password: process.env.MQTT_PASSWORD || undefined,
    reconnectPeriod: 5000,
  })

  client.on('connect', () => {
    console.log('[MQTT] Connected to', brokerUrl)
    client.subscribe('railway/sensors/#', (err) => {
      if (err) console.error('[MQTT] Subscribe error:', err)
    })
  })

  client.on('message', (topic, message) => {
    try {
      const data = JSON.parse(message.toString())
      const sensorId = data.sensor_id || topic.split('/').pop() || 'unknown'
      latestData[sensorId] = {
        ...data,
        topic,
        received_at: new Date().toISOString(),
      }
    } catch (e) {
      console.error('[MQTT] Parse error:', e)
    }
  })

  client.on('error', (err) => {
    console.error('[MQTT] Error:', err.message)
  })

  ctx.effect(() => () => {
    client.end(true)
  }, 'iot-mqtt-tool: close MQTT client')

  ctx.tools.register(defineTool({
    name: 'mqtt_get_sensor_data',
    description: 'Lấy dữ liệu mới nhất từ cảm biến IoT qua MQTT',
    parameters: {
      sensor_id: {
        type: 'string',
        required: true,
        description: 'ID cảm biến (ví dụ: cam-ranh-01)',
      },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const data = latestData[args.sensor_id]
      if (!data) {
        return `Cảm biến ${args.sensor_id} chưa có dữ liệu hoặc đang offline`
      }
      return JSON.stringify(data, null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'mqtt_list_sensors',
    description: 'Liệt kê tất cả cảm biến đang gửi dữ liệu qua MQTT',
    parameters: {},
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute() {
      const ids = Object.keys(latestData)
      if (ids.length === 0) return 'Chưa có cảm biến nào online'
      return ids.map(id => {
        const d = latestData[id]
        return `${id} | ${d.type || 'unknown'} | ${d.value} ${d.unit || ''} | ${d.received_at}`
      }).join('\n')
    },
  }))

  ctx.tools.register(defineTool({
    name: 'mqtt_check_sensor_threshold',
    description: 'Kiểm tra cảm biến có vượt ngưỡng không. Trả về true/false + dữ liệu',
    parameters: {
      sensor_id: { type: 'string', required: true },
      threshold: { type: 'number', required: true, description: 'Ngưỡng cảnh báo' },
      operator: {
        type: 'string',
        required: false,
        description: 'gt (lớn hơn) hoặc lt (nhỏ hơn). Mặc định gt',
        default: 'gt',
      },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const data = latestData[args.sensor_id]
      if (!data) return JSON.stringify({ alert: false, reason: 'no_data' })

      const value = Number(data.value)
      const op = args.operator || 'gt'
      const alert = op === 'gt' ? value > args.threshold : value < args.threshold

      return JSON.stringify({
        alert,
        sensor_id: args.sensor_id,
        value,
        threshold: args.threshold,
        operator: op,
        data,
      }, null, 2)
    },
  }))
}
