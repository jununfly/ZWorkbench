package market

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

const sampleIndicesJSON = `{"rc":0,"data":{"total":5,"diff":[
{"f2":3742.66,"f3":0.95,"f12":"000001","f14":"上证指数"},
{"f2":11957.07,"f3":1.19,"f12":"399001","f14":"深证成指"},
{"f2":2809.9,"f3":0.96,"f12":"399006","f14":"创业板指"},
{"f2":4197.46,"f3":0.75,"f12":"000300","f14":"沪深300"},
{"f2":1381.85,"f3":1.64,"f12":"000688","f14":"科创50"}]}}`

const sampleBreadthJSON = `{"rc":0,"data":{"diff":[{"f104":2057,"f105":273,"f106":27,"f107":3}]}}`

const sampleMoversJSON = `{"rc":0,"data":{"diff":[
{"f2":12.7,"f3":20.04,"f12":"300045","f14":"华力创通"},
{"f2":11.81,"f3":20.02,"f12":"300581","f14":"晨曦航空"}]}}`

const sampleSectorsJSON = `{"rc":0,"data":{"diff":[
{"f2":275.23,"f3":9.83,"f12":"BK1305","f14":"燃料电池"},
{"f2":3738.07,"f3":7.73,"f12":"BK1382","f14":"地面兵装Ⅲ"}]}}`

func TestFetchEastmoneyUnconfigured(t *testing.T) {
	_, err := FetchEastmoney(context.Background(), datasource.DefaultConfig())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("未配置应返回 ErrUnconfigured，得到 %v", err)
	}
}

func TestMapIndices(t *testing.T) {
	var r emListResponse
	if err := json.Unmarshal([]byte(sampleIndicesJSON), &r); err != nil {
		t.Fatalf("解码样例失败：%v", err)
	}
	idx := mapIndices(r)
	if len(idx) != 5 {
		t.Fatalf("期望 5 个指数，得到 %d", len(idx))
	}
	if idx[0].Name != "上证指数" || idx[0].Code != "000001" || idx[0].Value != 3742.66 || idx[0].ChangePct != 0.95 {
		t.Fatalf("首个指数映射错误：%+v", idx[0])
	}
}

func TestMapBreadth(t *testing.T) {
	var r emBreadthResponse
	if err := json.Unmarshal([]byte(sampleBreadthJSON), &r); err != nil {
		t.Fatalf("解码样例失败：%v", err)
	}
	b := mapBreadth(r)
	if b.Up != 2057 || b.Down != 273 || b.LimitUp != 27 || b.LimitDn != 3 {
		t.Fatalf("涨跌家数映射错误：%+v", b)
	}
}

func TestMapBreadthEmpty(t *testing.T) {
	var r emBreadthResponse
	b := mapBreadth(r)
	if b != (Breadth{}) {
		t.Fatalf("空响应应得零值，得到 %+v", b)
	}
}

func TestMapStockQuotes(t *testing.T) {
	var r emListResponse
	if err := json.Unmarshal([]byte(sampleMoversJSON), &r); err != nil {
		t.Fatalf("解码样例失败：%v", err)
	}
	q := mapStockQuotes(r)
	if len(q) != 2 || q[0].Code != "300045" || q[0].Name != "华力创通" || q[0].Price != 12.7 || q[0].ChangePct != 20.04 {
		t.Fatalf("个股映射错误：%+v", q)
	}
}

func TestMapSectors(t *testing.T) {
	var r emListResponse
	if err := json.Unmarshal([]byte(sampleSectorsJSON), &r); err != nil {
		t.Fatalf("解码样例失败：%v", err)
	}
	s := mapSectors(r)
	if len(s) != 2 || s[0].Name != "燃料电池" || s[0].ChangePct != 9.83 {
		t.Fatalf("板块映射错误：%+v", s)
	}
}

// TestFetchEastmoneyLive 对东方财富公开接口做一次真实调用，验证整条链路
// （超时 / 解码 / 映射）。默认跳过，避免测试依赖外网；设 ZW_LIVE_EM=1 才跑。
func TestFetchEastmoneyLive(t *testing.T) {
	if os.Getenv("ZW_LIVE_EM") != "1" {
		t.Skip("设 ZW_LIVE_EM=1 才对东方财富做真实调用")
	}
	cfg := datasource.Config{Enabled: true, BaseURL: "https://push2.eastmoney.com", TimeoutSec: 10}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	ov, err := FetchEastmoney(ctx, cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 真实调用失败：%v", err)
	}
	if len(ov.Indices) != 5 {
		t.Fatalf("真实指数数量异常：%d", len(ov.Indices))
	}
	if ov.Breadth.Up == 0 && ov.Breadth.Down == 0 {
		t.Fatalf("真实涨跌家数异常：%+v", ov.Breadth)
	}
	t.Logf("live snapshot: indices=%d up=%d down=%d gainers=%d losers=%d sectors=%d",
		len(ov.Indices), ov.Breadth.Up, ov.Breadth.Down, len(ov.TopGainers), len(ov.TopLosers), len(ov.Sectors))
}
