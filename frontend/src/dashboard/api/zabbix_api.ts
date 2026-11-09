import axios from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'
import type { ZabbixConfig, ZabbixRequest, ZabbixResponse } from '@/types/zabbixapi'
import type { MessageApiInjection } from 'naive-ui/es/message/src/MessageProvider'

class ZabbixAPI {
  private message: MessageApiInjection
  private client: AxiosInstance
  private auth_token: string | null = null
  private request_id: number = 0

  private constructor(url: string, token: string, message: MessageApiInjection) {
    this.message = message
    this.auth_token = token
    this.client = axios.create({
      baseURL: url,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json-rpc', // Zabbix 推荐的内容类型，虽然 application/json 通常也有效
      },
    })
  }

  static async create(config: ZabbixConfig, message: MessageApiInjection): Promise<ZabbixAPI> {
    if (config.token) {
      console.log('使用Token初始化')
      return new ZabbixAPI(config.url, config.token, message)
    } else if (config.username && config.password) {
      // 如果有账号密码，初始化时尝试登录
      const token = await this.login(config, message)
      return new ZabbixAPI(config.url, token, message)
    } else {
      throw new Error('初始化失败, 请提供token或者用户名/密码')
    }
  }

  /**
   * 1. 登录并获取 Auth Token
   */
  private static async login(config: ZabbixConfig, message: MessageApiInjection): Promise<string> {
    const payload: ZabbixRequest = {
      jsonrpc: '2.0',
      method: 'user.login',
      params: {
        user: config.username,
        password: config.password,
      },
      id: 1,
      auth: null, // 登录不需要 auth
    }

    try {
      const response = await axios.post(config.url, payload)
      const data: ZabbixResponse<string> = response.data

      if (data.error) {
        throw new Error(`Zabbix Login Failed: ${data.error.message}`)
      }

      if (!data.result) {
        throw new Error('Login failed: No token received')
      }

      const auth_token = data.result
      console.log('Zabbix Login Successful, Token:', auth_token)
      return auth_token
    } catch (error: any) {
      console.error('Zabbix API Connection Error:', error)
      message.error('Zabbix 连接失败: ' + (error.message || '未知错误'))
      throw error
    }
  }

  /**
   * 2. 通用请求方法 (核心)
   * 自动注入 auth, jsonrpc, id
   */
  async callMethod<T>(method: string, params: any = {}): Promise<T> {
    if (!this.auth_token && method !== 'user.login') {
      throw new Error('Not authenticated. Please login first.')
    }

    const payload: ZabbixRequest = {
      jsonrpc: '2.0',
      method: method,
      params: params,
      id: this.generateId(),
      auth: this.auth_token,
    }

    try {
      const response: AxiosResponse<ZabbixResponse<T>> = await this.client.post('', payload)
      const data = response.data

      // 处理 Zabbix 业务错误
      if (data.error) {
        const errorMsg = `[${data.error.code}] ${data.error.message}: ${data.error.data || ''}`
        console.error('Zabbix API Error:', errorMsg)

        // 特殊处理：如果 auth 失效 (通常错误码 -32602 或类似)，可以触发重新登录逻辑
        if (data.error.code === -32602 || data.error.message.includes('Not authorized')) {
          this.auth_token = null // 清空 token
          // 这里可以触发 Vue 的事件总线或 Pinia action 让用户重新登录
          this.message.warning('会话已过期，请重新登录')
        }

        throw new Error(errorMsg)
      }

      return data.result as T
    } catch (error: any) {
      // 网络错误或 Axios 错误
      if (!error.message.includes('Zabbix API Error')) {
        this.message.error('网络请求失败')
      } else if (error.message.includes('timeout')) {
        this.message.error('Zabbix API 响应超时!')
      }
      throw error
    }
  }

  /**
   * 生成唯一 ID
   */
  private generateId(): number {
    return ++this.request_id
  }

  /**
   * 获取当前 Token (供外部检查)
   */
  getToken(): string | null {
    return this.auth_token
  }

  /**
   * 登出
   */
  async logout(): Promise<void> {
    if (this.auth_token) {
      try {
        await this.callMethod('user.logout', {})
      } catch (e) {
        console.warn('Logout failed', e)
      } finally {
        this.auth_token = null
      }
    }
  }
}

// 导出单例或工厂函数
export default ZabbixAPI
