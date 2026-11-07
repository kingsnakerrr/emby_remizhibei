import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,createVNode:_createVNode,normalizeClass:_normalizeClass,createElementBlock:_createElementBlock,Fragment:_Fragment,renderList:_renderList} = await importShared('vue');


const _hoisted_1 = { class: "season-page" };
const _hoisted_2 = { class: "dashboard-grid" };
const _hoisted_3 = { class: "card-value" };
const _hoisted_4 = { class: "card-note" };
const _hoisted_5 = { class: "card-value" };
const _hoisted_6 = { class: "card-value" };
const _hoisted_7 = { class: "card-note" };
const _hoisted_8 = { class: "card-value" };
const _hoisted_9 = { class: "card-note" };
const _hoisted_10 = { class: "actions my-4" };
const _hoisted_11 = { key: 0 };
const _hoisted_12 = ["title"];
const _hoisted_13 = {
  key: 0,
  class: "table-actions"
};
const _hoisted_14 = {
  key: 1,
  class: "manual-actions"
};
const _hoisted_15 = ["title"];
const _hoisted_16 = { class: "record-window" };
const _hoisted_17 = {
  key: 0,
  class: "dialog-body"
};
const _hoisted_18 = {
  key: 1,
  class: "dialog-body"
};
const _hoisted_19 = {
  key: 2,
  class: "dialog-body"
};
const _hoisted_20 = {
  key: 3,
  class: "dialog-body"
};
const _hoisted_21 = {
  key: 4,
  class: "dialog-body"
};
const _hoisted_22 = { class: "mapping-grid mb-3" };

const {computed,onMounted,onUnmounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: { api: { type: Object, default: () => ({}) } },
  setup(__props) {

const props = __props;
const loading = ref(false);
const pending = ref(new Set());
const quarantineDir = ref('');
const quarantineLoaded = ref(false);
let statusBusy = false;
const activeJob = item => (state.value.active_jobs || []).find(j => j.series_rel === item.series_rel);
const rowBusy = item => pending.value.has(item.series_rel) || Boolean(activeJob(item));
const rowFailure = item => (state.value.failed_jobs || []).find(j => j.series_rel === item.series_rel)?.message || '';
const message = ref('');
const error = ref('');
const dialog = ref('');
const recordTab = ref('scan');
const scanSearch = ref('');
const overrideOpen = ref(false);
const rulesOpen = ref(false);
const overrideForm = ref({
  tmdb_id: 0, title: '', counts: '', target_tmdb_id: '', target_season: '',
  target_title: '', source: '人工核对', note: '',
});
const state = ref({
  headline: '正在读取状态…', summary: {}, scan_results: [], active_jobs: [],
  success_jobs: [], failed_jobs: [], scan_logs: [], other_logs: [], actions: [], season_overrides: [],
});
let timer;

const summary = computed(() => state.value.summary || {});
const dialogOpen = computed({
  get: () => Boolean(dialog.value),
  set: value => { if (!value) dialog.value = ''; },
});
const unwrap = response => response?.data?.data ?? response?.data ?? response;
const formatDuration = row => row?.duration_seconds === undefined ? '—' : `${row.duration_seconds} 秒`;
const scanHeaders = [
  { title: '媒体', key: 'name' },
  { title: '当前季度', key: 'current_summary', width: 230 },
  { title: '判定季度', key: 'official_summary', width: 230 },
  { title: '判断', key: 'status', width: 150 },
  { title: '操作', key: 'actions', sortable: false, width: 170 },
];
const jobHeaders = [
  { title: '媒体', key: 'name' },
  { title: '开始时间', key: 'started_at', width: 190 },
  { title: '结束时间', key: 'finished_at', width: 190 },
  { title: '耗时', key: 'duration', width: 100 },
  { title: '结果', key: 'message' },
];
const operationHeaders = [
  { title: '任务', key: 'title', width: 190 },
  { title: '开始时间', key: 'started_at', width: 190 },
  { title: '结束时间', key: 'finished_at', width: 190 },
  { title: '耗时', key: 'duration', width: 100 },
  { title: '结果', key: 'detail' },
];

async function loadStatus(silent = false) {
  if (statusBusy) return
  statusBusy = true;
  if (!silent) loading.value = true;
  try {
    const response = await props.api.post('plugin/TVSeasonRepair/ui_status', {});
    state.value = unwrap(response) || state.value;
    if (!quarantineLoaded.value) {
      quarantineDir.value = state.value.quarantine_dir || '';
      quarantineLoaded.value = true;
    }
    error.value = '';
  } catch (err) {
    error.value = err?.message || '读取状态失败';
  } finally {
    statusBusy = false;
    if (!silent) loading.value = false;
  }
}

async function run(path, payload = {}, successText = '') {
  const key = path === 'apply' ? payload.series_rel : '';
  if (key && rowBusy({ series_rel: key })) return
  if (key) pending.value.add(key);
  loading.value = true;
  error.value = '';
  message.value = '';
  try {
    const response = await props.api.post(`plugin/TVSeasonRepair/${path}`, payload);
    const body = response?.data ?? response;
    if (body?.success === false) error.value = body.message || '操作失败';
    else message.value = body?.message || successText || '操作已提交';
    await loadStatus(true);
  } catch (err) {
    error.value = err?.message || '操作失败';
  } finally {
    if (key) pending.value.delete(key);
    loading.value = false;
  }
}

function openDialog(name, tab = '') {
  dialog.value = name;
  if (tab) recordTab.value = tab;
}

function openOverride(item) {
  const saved = (state.value.season_overrides || []).find(row => Number(row.tmdb_id) === Number(item.tmdb_id));
  overrideForm.value = {
    tmdb_id: Number(item.tmdb_id),
    title: item.name || saved?.title || '',
    counts: saved?.counts?.join(',') || '',
    target_tmdb_id: saved?.target_tmdb_id || '',
    target_season: saved?.target_season || '',
    target_title: saved?.target_title || '',
    source: saved?.source || '人工核对',
    note: saved?.note || '',
  };
  overrideOpen.value = true;
}

async function saveOverride(remove = false) {
  const payload = { ...overrideForm.value, delete: remove };
  await run('season_override', payload);
  if (!error.value) overrideOpen.value = false;
}

async function removeOverride(item) {
  overrideForm.value = {
    ...item,
    counts: (item.counts || []).join(','),
    target_tmdb_id: item.target_tmdb_id || '',
    target_season: item.target_season || '',
  };
  await saveOverride(true);
}

onMounted(() => {
  loadStatus();
  timer = window.setInterval(() => loadStatus(true), 3000);
});
onUnmounted(() => window.clearInterval(timer));

return (_ctx, _cache) => {
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VDialog = _resolveComponent("VDialog");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VCardActions = _resolveComponent("VCardActions");
  const _component_VListItem = _resolveComponent("VListItem");
  const _component_VList = _resolveComponent("VList");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (loading.value)
      ? (_openBlock(), _createBlock(_component_VProgressLinear, {
          key: 0,
          indeterminate: "",
          class: "mb-3"
        }))
      : _createCommentVNode("", true),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 1,
          type: "error",
          variant: "tonal",
          closable: "",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (message.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 2,
          type: "success",
          variant: "tonal",
          closable: "",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(message.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_2, [
      _createVNode(_component_VCard, {
        class: "dash-card card-scan",
        onClick: _cache[0] || (_cache[0] = $event => (openDialog('scan')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[29] || (_cache[29] = _createElementVNode("div", { class: "card-label" }, "扫描候选", -1)),
              _createElementVNode("div", _hoisted_3, _toDisplayString(summary.value.candidate_count || 0), 1),
              _createElementVNode("div", _hoisted_4, "可安全修复 " + _toDisplayString(summary.value.safe_count || 0) + " 部", 1),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "dash-card card-active",
        onClick: _cache[1] || (_cache[1] = $event => (openDialog('active')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[30] || (_cache[30] = _createElementVNode("div", { class: "card-label" }, "处理中", -1)),
              _createElementVNode("div", _hoisted_5, _toDisplayString(summary.value.active_count || 0), 1),
              _cache[31] || (_cache[31] = _createElementVNode("div", { class: "card-note" }, "查看队列与实时状态", -1)),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "dash-card card-result",
        onClick: _cache[2] || (_cache[2] = $event => (openDialog('records', 'success')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[32] || (_cache[32] = _createElementVNode("div", { class: "card-label" }, "修复结果", -1)),
              _createElementVNode("div", _hoisted_6, _toDisplayString(summary.value.success_count || 0), 1),
              _createElementVNode("div", _hoisted_7, "失败 " + _toDisplayString(summary.value.failed_count || 0) + " 条", 1),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "dash-card card-log",
        onClick: _cache[3] || (_cache[3] = $event => (openDialog('records', 'scan')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[33] || (_cache[33] = _createElementVNode("div", { class: "card-label" }, "任务记录", -1)),
              _createElementVNode("div", _hoisted_8, _toDisplayString(summary.value.log_count || 0), 1),
              _createElementVNode("div", _hoisted_9, "可回滚 " + _toDisplayString(summary.value.rollback_count || 0) + " 条", 1),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _createElementVNode("div", _hoisted_10, [
      _createVNode(_component_VBtn, {
        class: "action-primary",
        "prepend-icon": "mdi-magnify",
        onClick: _cache[4] || (_cache[4] = $event => (run('scan')))
      }, {
        default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
          _createTextVNode("扫描媒体库", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-info",
        "prepend-icon": "mdi-eye-outline",
        onClick: _cache[5] || (_cache[5] = $event => (run('batch', { execute: false })))
      }, {
        default: _withCtx(() => [...(_cache[35] || (_cache[35] = [
          _createTextVNode("预览安全项目", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-warning",
        "prepend-icon": "mdi-tools",
        onClick: _cache[6] || (_cache[6] = $event => (run('batch', { execute: true })))
      }, {
        default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
          _createTextVNode("批量修复", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-info",
        "prepend-icon": "mdi-tune",
        onClick: _cache[7] || (_cache[7] = $event => (rulesOpen.value = true))
      }, {
        default: _withCtx(() => [
          _createTextVNode("集数与映射规则（" + _toDisplayString(state.value.season_overrides?.length || 0) + "）", 1)
        ]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-log",
        "prepend-icon": "mdi-text-box-outline",
        onClick: _cache[8] || (_cache[8] = $event => (openDialog('records', 'scan')))
      }, {
        default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
          _createTextVNode("查看任务记录", -1)
        ]))]),
        _: 1
      })
    ]),
    _createVNode(_component_VAlert, {
      type: "info",
      variant: "tonal",
      class: "headline"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(state.value.headline), 1)
      ]),
      _: 1
    }),
    _createVNode(_component_VCard, { class: "my-4 pa-4" }, {
      default: _withCtx(() => [
        _cache[39] || (_cache[39] = _createElementVNode("div", { class: "mb-2" }, "异常文件云盘隔离目录", -1)),
        _createVNode(_component_VTextField, {
          modelValue: quarantineDir.value,
          "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((quarantineDir).value = $event)),
          label: "CD2 云盘真实路径（留空使用原隔离目录）",
          placeholder: "/CloudNAS/CloudDrive/GoogleDrive/zero/media/symedia_gd/tvshows_error",
          "hide-details": ""
        }, null, 8, ["modelValue"]),
        _cache[40] || (_cache[40] = _createElementVNode("div", { class: "my-2" }, "只隔离超出集数的文件，保留分类 / 剧名 / 动作号 / 季目录。不会移动整部正常剧集。请使用 Emby、Symedia 扫描范围之外的目录；/home/symedia_gd 是本地 STRM，不能作为视频隔离路径。", -1)),
        _createVNode(_component_VBtn, {
          disabled: loading.value || !!state.value.active_jobs?.length,
          onClick: _cache[10] || (_cache[10] = $event => (run('quarantine', { quarantine_dir: quarantineDir.value })))
        }, {
          default: _withCtx(() => [...(_cache[38] || (_cache[38] = [
            _createTextVNode("保存隔离目录", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"])
      ]),
      _: 1
    }),
    _createVNode(_component_VDialog, {
      modelValue: dialogOpen.value,
      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((dialogOpen).value = $event)),
      "max-width": "1240",
      scrollable: ""
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "dialog-card" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "dialog-title" }, {
              default: _withCtx(() => [
                _createElementVNode("span", null, _toDisplayString(dialog.value === 'scan' ? '扫描结果' : dialog.value === 'active' ? '处理任务' : '任务记录'), 1),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  onClick: _cache[11] || (_cache[11] = $event => (dialog.value = ''))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            (dialog.value === 'scan')
              ? (_openBlock(), _createBlock(_component_VCardText, {
                  key: 0,
                  class: "dialog-body"
                }, {
                  default: _withCtx(() => [
                    (error.value)
                      ? (_openBlock(), _createBlock(_component_VAlert, {
                          key: 0,
                          type: "error",
                          class: "mb-3"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(error.value), 1)
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true),
                    (message.value)
                      ? (_openBlock(), _createBlock(_component_VAlert, {
                          key: 1,
                          type: "info",
                          class: "mb-3"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(message.value), 1)
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true),
                    _createVNode(_component_VAlert, {
                      type: "info",
                      variant: "tonal",
                      class: "mb-3"
                    }, {
                      default: _withCtx(() => [...(_cache[41] || (_cache[41] = [
                        _createTextVNode("默认使用媒体当前绑定的 TMDB。若它是残缺的重复条目，可映射到正确系列的指定季度；只有找不到正确条目时才使用人工集数。", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_VTextField, {
                      modelValue: scanSearch.value,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((scanSearch).value = $event)),
                      "prepend-inner-icon": "mdi-magnify",
                      label: "搜索媒体",
                      variant: "outlined",
                      density: "comfortable",
                      "hide-details": "",
                      class: "mb-3"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VDataTable, {
                      headers: scanHeaders,
                      items: state.value.scan_results,
                      search: scanSearch.value,
                      "items-per-page": 20,
                      class: "data-table"
                    }, {
                      "item.status": _withCtx(({ item }) => [
                        _createElementVNode("span", {
                          class: _normalizeClass(item.safe ? 'status-safe' : 'status-manual')
                        }, _toDisplayString(rowBusy(item) ? '处理中' : item.safe ? '可修复' : '人工核对'), 3),
                        (activeJob(item))
                          ? (_openBlock(), _createElementBlock("div", _hoisted_11, _toDisplayString(activeJob(item).message), 1))
                          : (rowFailure(item))
                            ? (_openBlock(), _createElementBlock("div", {
                                key: 1,
                                title: rowFailure(item)
                              }, "上次失败，详情见失败记录", 8, _hoisted_12))
                            : _createCommentVNode("", true)
                      ]),
                      "item.actions": _withCtx(({ item }) => [
                        (item.safe)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_13, [
                              _createVNode(_component_VBtn, {
                                size: "small",
                                disabled: rowBusy(item),
                                class: "table-preview",
                                onClick: $event => (run('apply', { series_rel: item.series_rel, execute: false }))
                              }, {
                                default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                                  _createTextVNode("预览", -1)
                                ]))]),
                                _: 1
                              }, 8, ["disabled", "onClick"]),
                              _createVNode(_component_VBtn, {
                                size: "small",
                                disabled: rowBusy(item),
                                loading: rowBusy(item),
                                class: "table-fix",
                                onClick: $event => (run('apply', { series_rel: item.series_rel, execute: true }))
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(rowBusy(item) ? '处理中' : '修复'), 1)
                                ]),
                                _: 2
                              }, 1032, ["disabled", "loading", "onClick"])
                            ]))
                          : (_openBlock(), _createElementBlock("div", _hoisted_14, [
                              _createElementVNode("span", {
                                class: "reason-text",
                                title: item.reason
                              }, _toDisplayString(item.reason), 9, _hoisted_15),
                              _createVNode(_component_VBtn, {
                                size: "small",
                                class: "table-override",
                                onClick: $event => (openOverride(item))
                              }, {
                                default: _withCtx(() => [...(_cache[43] || (_cache[43] = [
                                  _createTextVNode("设置规则", -1)
                                ]))]),
                                _: 1
                              }, 8, ["onClick"])
                            ]))
                      ]),
                      _: 1
                    }, 8, ["items", "search"])
                  ]),
                  _: 1
                }))
              : (dialog.value === 'active')
                ? (_openBlock(), _createBlock(_component_VCardText, {
                    key: 1,
                    class: "dialog-body"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VDataTable, {
                        headers: jobHeaders,
                        items: state.value.active_jobs,
                        "items-per-page": 20,
                        class: "data-table"
                      }, {
                        "item.started_at": _withCtx(({ item }) => [
                          _createTextVNode(_toDisplayString(item.started_at || item.created_at || '—'), 1)
                        ]),
                        "item.finished_at": _withCtx(() => [...(_cache[44] || (_cache[44] = [
                          _createTextVNode("—", -1)
                        ]))]),
                        "item.duration": _withCtx(() => [...(_cache[45] || (_cache[45] = [
                          _createTextVNode("运行中", -1)
                        ]))]),
                        "no-data": _withCtx(() => [...(_cache[46] || (_cache[46] = [
                          _createElementVNode("div", { class: "empty" }, "当前没有处理中的任务", -1)
                        ]))]),
                        _: 1
                      }, 8, ["items"])
                    ]),
                    _: 1
                  }))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                    _createVNode(_component_VTabs, {
                      modelValue: recordTab.value,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((recordTab).value = $event)),
                      class: "record-tabs",
                      "show-arrows": ""
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VTab, { value: "scan" }, {
                          default: _withCtx(() => [...(_cache[47] || (_cache[47] = [
                            _createTextVNode("扫描日志", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "success" }, {
                          default: _withCtx(() => [...(_cache[48] || (_cache[48] = [
                            _createTextVNode("成功记录", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "failed" }, {
                          default: _withCtx(() => [...(_cache[49] || (_cache[49] = [
                            _createTextVNode("失败记录", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "operation" }, {
                          default: _withCtx(() => [...(_cache[50] || (_cache[50] = [
                            _createTextVNode("预览与回滚", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "rollback" }, {
                          default: _withCtx(() => [...(_cache[51] || (_cache[51] = [
                            _createTextVNode("最近修复", -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }, 8, ["modelValue"]),
                    _createVNode(_component_VDivider),
                    _createElementVNode("div", _hoisted_16, [
                      (recordTab.value === 'scan')
                        ? (_openBlock(), _createElementBlock("div", _hoisted_17, [
                            _createVNode(_component_VDataTable, {
                              headers: operationHeaders,
                              items: state.value.scan_logs,
                              "items-per-page": 20,
                              class: "data-table"
                            }, {
                              "item.duration": _withCtx(({ item }) => [
                                _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                              ]),
                              "no-data": _withCtx(() => [...(_cache[52] || (_cache[52] = [
                                _createElementVNode("div", { class: "empty" }, "暂无扫描日志", -1)
                              ]))]),
                              _: 1
                            }, 8, ["items"])
                          ]))
                        : (recordTab.value === 'success')
                          ? (_openBlock(), _createElementBlock("div", _hoisted_18, [
                              _createVNode(_component_VDataTable, {
                                headers: jobHeaders,
                                items: state.value.success_jobs,
                                "items-per-page": 20,
                                class: "data-table"
                              }, {
                                "item.started_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.started_at || item.created_at), 1)
                                ]),
                                "item.finished_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.finished_at || item.updated_at), 1)
                                ]),
                                "item.duration": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                ]),
                                "no-data": _withCtx(() => [...(_cache[53] || (_cache[53] = [
                                  _createElementVNode("div", { class: "empty" }, "暂无成功记录", -1)
                                ]))]),
                                _: 1
                              }, 8, ["items"])
                            ]))
                          : (recordTab.value === 'failed')
                            ? (_openBlock(), _createElementBlock("div", _hoisted_19, [
                                _createVNode(_component_VDataTable, {
                                  headers: jobHeaders,
                                  items: state.value.failed_jobs,
                                  "items-per-page": 20,
                                  class: "data-table"
                                }, {
                                  "item.started_at": _withCtx(({ item }) => [
                                    _createTextVNode(_toDisplayString(item.started_at || item.created_at), 1)
                                  ]),
                                  "item.finished_at": _withCtx(({ item }) => [
                                    _createTextVNode(_toDisplayString(item.finished_at || item.updated_at), 1)
                                  ]),
                                  "item.duration": _withCtx(({ item }) => [
                                    _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                  ]),
                                  "no-data": _withCtx(() => [...(_cache[54] || (_cache[54] = [
                                    _createElementVNode("div", { class: "empty" }, "暂无失败记录", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["items"])
                              ]))
                            : (recordTab.value === 'operation')
                              ? (_openBlock(), _createElementBlock("div", _hoisted_20, [
                                  _createVNode(_component_VDataTable, {
                                    headers: operationHeaders,
                                    items: state.value.other_logs,
                                    "items-per-page": 20,
                                    class: "data-table"
                                  }, {
                                    "item.duration": _withCtx(({ item }) => [
                                      _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                    ]),
                                    "no-data": _withCtx(() => [...(_cache[55] || (_cache[55] = [
                                      _createElementVNode("div", { class: "empty" }, "暂无预览或回滚日志", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["items"])
                                ]))
                              : (_openBlock(), _createElementBlock("div", _hoisted_21, [
                                  _createVNode(_component_VDataTable, {
                                    headers: [{ title: '媒体', key: 'name' }, { title: '完成时间', key: 'finished_at', width: 200 }, { title: '动作号', key: 'action_id', width: 260 }, { title: '操作', key: 'actions', sortable: false, width: 100 }],
                                    items: state.value.actions,
                                    "items-per-page": 20,
                                    class: "data-table"
                                  }, {
                                    "item.finished_at": _withCtx(({ item }) => [
                                      _createTextVNode(_toDisplayString(item.finished_at || '旧记录'), 1)
                                    ]),
                                    "item.actions": _withCtx(({ item }) => [
                                      _createVNode(_component_VBtn, {
                                        size: "small",
                                        class: "table-undo",
                                        onClick: $event => (run('undo', { action_id: item.action_id }))
                                      }, {
                                        default: _withCtx(() => [...(_cache[56] || (_cache[56] = [
                                          _createTextVNode("回滚", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["onClick"])
                                    ]),
                                    "no-data": _withCtx(() => [...(_cache[57] || (_cache[57] = [
                                      _createElementVNode("div", { class: "empty" }, "暂无可回滚记录", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["items"])
                                ]))
                    ])
                  ], 64))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: overrideOpen.value,
      "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((overrideOpen).value = $event)),
      "max-width": "620"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "dialog-card" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "dialog-title" }, {
              default: _withCtx(() => [
                _cache[58] || (_cache[58] = _createElementVNode("span", null, "集数与正确季度映射", -1)),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  onClick: _cache[15] || (_cache[15] = $event => (overrideOpen.value = false))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "dialog-body" }, {
              default: _withCtx(() => [
                _createVNode(_component_VAlert, {
                  type: "warning",
                  variant: "tonal",
                  class: "mb-4"
                }, {
                  default: _withCtx(() => [...(_cache[59] || (_cache[59] = [
                    _createTextVNode("优先填写“正确 TMDB ID + 正确季度”。例如残缺的 291141/S01 对应完整系列 19389/S03；插件会读取正确季度的集数。没有正确条目时，才在人工集数中填写“38”或“20,20,18”。", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTextField, {
                  modelValue: overrideForm.value.title,
                  "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((overrideForm.value.title) = $event)),
                  label: "媒体",
                  readonly: "",
                  class: "mb-3"
                }, null, 8, ["modelValue"]),
                _createElementVNode("div", _hoisted_22, [
                  _createVNode(_component_VTextField, {
                    modelValue: overrideForm.value.target_tmdb_id,
                    "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((overrideForm.value.target_tmdb_id) = $event)),
                    type: "number",
                    label: "正确系列 TMDB ID",
                    placeholder: "例如：19389"
                  }, null, 8, ["modelValue"]),
                  _createVNode(_component_VTextField, {
                    modelValue: overrideForm.value.target_season,
                    "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((overrideForm.value.target_season) = $event)),
                    type: "number",
                    label: "正确季度",
                    placeholder: "例如：3"
                  }, null, 8, ["modelValue"])
                ]),
                _createVNode(_component_VTextField, {
                  modelValue: overrideForm.value.target_title,
                  "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((overrideForm.value.target_title) = $event)),
                  label: "正确系列名称（可选）",
                  placeholder: "例如：我和僵尸有个约会",
                  class: "mb-3"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_VTextField, {
                  modelValue: overrideForm.value.counts,
                  "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((overrideForm.value.counts) = $event)),
                  label: "人工集数（映射留空时使用）",
                  placeholder: "例如：38 或 20,20,18",
                  class: "mb-3"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_VTextField, {
                  modelValue: overrideForm.value.source,
                  "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((overrideForm.value.source) = $event)),
                  label: "核对来源",
                  placeholder: "例如：百度百科 / 官方资料",
                  class: "mb-3"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_VTextarea, {
                  modelValue: overrideForm.value.note,
                  "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((overrideForm.value.note) = $event)),
                  label: "备注（可选）",
                  rows: "2"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, { class: "px-4 pb-4" }, {
              default: _withCtx(() => [
                _createVNode(_component_VBtn, {
                  color: "primary",
                  variant: "flat",
                  onClick: _cache[23] || (_cache[23] = $event => (saveOverride(false)))
                }, {
                  default: _withCtx(() => [...(_cache[60] || (_cache[60] = [
                    _createTextVNode("保存规则", -1)
                  ]))]),
                  _: 1
                }),
                ((state.value.season_overrides || []).some(row => Number(row.tmdb_id) === Number(overrideForm.value.tmdb_id)))
                  ? (_openBlock(), _createBlock(_component_VBtn, {
                      key: 0,
                      color: "error",
                      variant: "tonal",
                      onClick: _cache[24] || (_cache[24] = $event => (saveOverride(true)))
                    }, {
                      default: _withCtx(() => [...(_cache[61] || (_cache[61] = [
                        _createTextVNode("删除规则", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[25] || (_cache[25] = $event => (overrideOpen.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[62] || (_cache[62] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: rulesOpen.value,
      "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((rulesOpen).value = $event)),
      "max-width": "760",
      scrollable: ""
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "dialog-card" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "dialog-title" }, {
              default: _withCtx(() => [
                _cache[63] || (_cache[63] = _createElementVNode("span", null, "集数与映射规则", -1)),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  onClick: _cache[27] || (_cache[27] = $event => (rulesOpen.value = false))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "dialog-body" }, {
              default: _withCtx(() => [
                (!state.value.season_overrides?.length)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 0,
                      type: "info",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [...(_cache[64] || (_cache[64] = [
                        _createTextVNode("尚未设置人工规则。", -1)
                      ]))]),
                      _: 1
                    }))
                  : (_openBlock(), _createBlock(_component_VList, {
                      key: 1,
                      "bg-color": "transparent"
                    }, {
                      default: _withCtx(() => [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.season_overrides, (item) => {
                          return (_openBlock(), _createBlock(_component_VListItem, {
                            key: item.tmdb_id,
                            title: `${item.title || '未命名'} · TMDB ${item.tmdb_id}`,
                            subtitle: item.target_tmdb_id ? `映射：TMDB ${item.target_tmdb_id} S${String(item.target_season).padStart(2, '0')}（${item.counts?.[0] || '?'} 集）｜来源：${item.source || '人工核对'}｜更新：${item.updated_at}` : `人工季度：${item.counts.join(', ')}｜来源：${item.source || '人工核对'}｜更新：${item.updated_at}`
                          }, {
                            append: _withCtx(() => [
                              _createVNode(_component_VBtn, {
                                color: "error",
                                variant: "tonal",
                                size: "small",
                                onClick: $event => (removeOverride(item))
                              }, {
                                default: _withCtx(() => [...(_cache[65] || (_cache[65] = [
                                  _createTextVNode("删除", -1)
                                ]))]),
                                _: 1
                              }, 8, ["onClick"])
                            ]),
                            _: 2
                          }, 1032, ["title", "subtitle"]))
                        }), 128))
                      ]),
                      _: 1
                    }))
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-8d397efa"]]);

export { Page as default };
