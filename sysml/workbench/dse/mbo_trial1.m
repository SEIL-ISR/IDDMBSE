
%Imported the Design Matrix B with negated values of MoEs 2 and 4 from Excel

res1 = readmatrix("plot4met.csv")


[A b]=prtp(res1)
writematrix(b,'pareto_designs.csv')
writematrix(A,'pareto_design_evals.csv')
%%
% %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% % 4-D Plot of all design options for Visualization
% pathlen = B(:,1);                              % cost MoE
% Lb = -B(:,2);                                % battery life MoE
% Tc = B(:,3);                       % Charging Time MoE
% 
% 
% scatter3(cost2,Lb,Tc)    % draw the scatter plot
% ax = gca;
% ax.XDir = 'reverse';
% view(-31,14)
% xlabel('Cost ($)')
% ylabel('Battery Life (Hrs)')
% zlabel('Charging Time (min)')

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Pareto Front

% scatter3(cost2,Lb,Tc) 

%%


function [A varargout]=prtp(B)
A=[]; varargout{1}=[];
sz1=size(B,1);
jj=0; kk(sz1)=0;
c(sz1,size(B,2))=0;
bb=c;
for k=1:sz1
  j=0;
  ak=B(k,:);
  for i=1:sz1
    if i~=k
      j=j+1;
      bb(j,:)=ak-B(i,:);
    end
  end
  if any(bb(1:j,:)'<0)
    jj=jj+1;
    c(jj,:)=ak;
    kk(jj)=k;
  end
end
if jj
  A=c(1:jj,:);
  varargout{1}=kk(1:jj);
else
  warning('Points:Pareto',...
    'There are no Pareto points. The result is an empty matrix.')
end

end