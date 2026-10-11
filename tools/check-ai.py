"""Check AI setup without displaying credentials; one small request by default."""
import argparse
import sys
import serve

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-only', action='store_true', help='validate local settings without contacting the provider')
    args = parser.parse_args(argv)
    try:
        config = serve.read_current_config()
        if args.config_only:
            print('本地 AI 配置检查通过；尚未验证服务商连接。')
        else:
            serve.call_model(config, '连接测试：请只回复 OK。', max_tokens=128)
            print('AI 连接测试成功：已收到模型回复。可以启动本机服务并提问。')
        return 0
    except (serve.InputError, serve.ProviderError) as error:
        print('AI 检查失败：' + str(error), file=sys.stderr)
        return 1
    except Exception:
        print('AI 检查失败：配置格式或服务响应异常，请检查 AI 接入指南。', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
