
las= [1000 1500 1500 2000]
lid= [2200 2500 1500 1800]
cam= [1500 2000]
dep = [540 800 1920]

cost = zeros(71,1);
p=1;
for i =1:4
    for j=1:4
        for k= 1:2
            for l= 1:3
                cost(p) = las(i)+lid(j)+cam(k)+dep(l)
                p=p+1
            end
        end
    end
end

cost2= cost(1:71)