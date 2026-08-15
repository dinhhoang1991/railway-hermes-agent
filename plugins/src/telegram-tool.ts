import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'telegram-tool'
export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'send_telegram',
    description: 'Gửi tin nhắn cảnh báo hoặc thông báo qua Telegram Bot. Hỗ trợ HTML.',
    parameters: {
      message: {
        type: 'string',
        required: true,
        description: 'Nội dung tin nhắn cần gửi'
      },
      chat_id: {
        type: 'string',
        required: false,
        description: 'Chat ID (nếu không truyền sẽ lấy từ biến môi trường TELEGRAM_CHAT_ID)'
      },
      parse_mode: {
        type: 'string',
        required: false,
        description: 'HTML hoặc Markdown. Mặc định HTML',
        default: 'HTML'
      }
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const token = process.env.TELEGRAM_BOT_TOKEN
      const defaultChatId = process.env.TELEGRAM_CHAT_ID
      const chatId = args.chat_id || defaultChatId

      if (!token) {
        return 'Lỗi: Thiếu biến môi trường TELEGRAM_BOT_TOKEN'
      }
      if (!chatId) {
        return 'Lỗi: Thiếu TELEGRAM_CHAT_ID (truyền qua tham số hoặc biến môi trường)'
      }

      try {
        const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: chatId,
            text: args.message,
            parse_mode: args.parse_mode || 'HTML',
          }),
        })

        if (!response.ok) {
          const errorText = await response.text()
          return `Gửi Telegram thất bại (${response.status}): ${errorText}`
        }

        return '✅ Đã gửi tin nhắn Telegram thành công'
      } catch (error: any) {
        return `Lỗi kết nối Telegram: ${error.message || String(error)}`
      }
    },
  }))
}
