import { ElMessage } from 'element-plus'
import router from '../router'
import axios from "axios";
import { clearSession } from './session'

const request = axios.create({
    baseURL: import.meta.env.VITE_BASE_URL,
    withCredentials: true,
    timeout: 30000  // 后台接口超时时间设置
})

// request 拦截器
// 可以自请求发送前对请求做一些处理
request.interceptors.request.use(config => {
    // Content-Type 交给 axios 按请求体类型自动设置（JSON 对象→json，FormData→multipart）
    return config
}, error => {
    return Promise.reject(error)
});

// response 拦截器
// 可以在接口响应后统一处理结果
request.interceptors.response.use(
    response => {
        let res = response.data;
        // 兼容服务端返回的字符串数据
        if (typeof res === 'string') {
            res = res ? JSON.parse(res) : res
        }
        return res;
    },
    error => {
        if (error.response?.status === 401) {
            clearSession()
            if (router.currentRoute.value.path !== '/login') {
                ElMessage.error(error.response?.data?.msg || '登录状态已失效，请重新登录')
                router.push('/login')
            }
        } else if (axios.isCancel(error)) {
            return Promise.reject(error)
        } else if (!error.config?.skipErrorToast) {
            const message = error.response?.data?.msg || error.response?.data?.detail || '请求失败，请稍后重试'
            ElMessage.error(message)
        }
        return Promise.reject(error)
    }
)


export default request
