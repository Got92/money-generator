import test from 'node:test';
import assert from 'node:assert/strict';
import {compareTargets} from '../src/target-allocation.js';
test('targets compare real positions, signed cash, unknown metadata and thresholds',()=>{
 const positions=[{ticker:'A',value:80,quote:{sector:'Tech',industry:'Tools'}},{ticker:'B',value:20,quote:{}}];
 const targets=[{dimension:'position',key:'A',min:.6,target:.7,max:.8},{dimension:'sector',key:'Tech',min:.7,target:.8,max:.9},{dimension:'industry',key:'Missing',min:.1,target:.2,max:.3}];
 const result=compareTargets(positions,[{currency:'EUR',value:-20}],{basis:'total',targets});
 assert.equal(result.position.targets[0].actual,1);assert.equal(result.position.targets[0].flag,'above');
 assert.equal(result.sector.groups.find(g=>g.category===null).weight,.25);
 assert.equal(result.industry.targets[0].flag,'unavailable');
 assert.equal(result.sector.targets[0].actual,null);
 const missing=compareTargets([{ticker:'A',value:null}],[],{basis:'invested',targets});
 assert.equal(missing.position.targets[0].actual,null);assert.equal(missing.position.targets[0].flag,'unavailable');
});
