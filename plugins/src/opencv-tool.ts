import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { exec } from 'node:child_process'
import { promisify } from 'node:util'

const execAsync = promisify(exec)

export const name = 'opencv-tool'
export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'run_opencv_detect',
    description: 'Chạy script Python OpenCV để phát hiện sạt lở / chuyển động bất thường. Trả về stdout của script.',
    parameters: {
      script_path: {
        type: 'string',
        required: true,
        description: 'Đường dẫn tuyệt đối tới file Python (.py)'
      },
      image_path: {
        type: 'string',
        description: 'Đường dẫn tới ảnh cần phân tích'
      },
      extra_args: {
        type: 'string',
        description: 'Các tham số bổ sung truyền cho script (ví dụ: --threshold 0.65 --save-result)'
      }
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const parts: string[] = ['python3', `"${args.script_path}"`]

      if (args.image_path) {
        parts.push(`--image "${args.image_path}"`)
      }
      if (args.extra_args) {
        parts.push(args.extra_args)
      }

      const command = parts.join(' ')

      try {
        const { stdout, stderr } = await execAsync(command, {
          timeout: 90_000,
          maxBuffer: 1024 * 1024 * 5,
        })

        let result = ''
        if (stderr && stderr.trim()) {
          result += `⚠️ stderr:\n${stderr.trim()}\n\n`
        }
        result += stdout ? stdout.trim() : 'Script chạy thành công (không có output)'

        return result
      } catch (error: any) {
        return `❌ Lỗi khi chạy OpenCV script:\n${error.message || String(error)}`
      }
    },
  }))
}
