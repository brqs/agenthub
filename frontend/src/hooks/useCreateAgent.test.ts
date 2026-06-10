import { buildAgentConfig } from './useCreateAgent';

describe('buildAgentConfig', () => {
  it('builds server agent wrapper config', () => {
    expect(
      buildAgentConfig({
        name: 'Frontend Wrapper',
        provider: 'opencode',
        baseAgentId: 'opencode-helper',
        capabilities: ['前端实现'],
        systemPrompt: '角色：前端实现助手',
        wrapperProfile: {
          role: '前端实现助手',
          purpose: '实现网页',
          planning_profile: '网页实现任务优先调用',
          planning_strengths: ['静态页面'],
          planning_weaknesses: ['产品规划'],
          preferred_task_types: ['实现'],
          capabilities: ['前端实现'],
          output_style: '给出文件和验收说明',
          boundaries: ['不改后端'],
        },
      }),
    ).toEqual({
      custom_agent_mode: 'server_agent_wrapper',
      base_agent_id: 'opencode-helper',
      wrapper_profile: {
        role: '前端实现助手',
        purpose: '实现网页',
        planning_profile: '网页实现任务优先调用',
        planning_strengths: ['静态页面'],
        planning_weaknesses: ['产品规划'],
        preferred_task_types: ['实现'],
        capabilities: ['前端实现'],
        output_style: '给出文件和验收说明',
        boundaries: ['不改后端'],
      },
    });
  });
});
