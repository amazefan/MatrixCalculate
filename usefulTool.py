import pickle
import h5py
import h5sparse
import gc
import sys
import dask.array as da
import numpy as np
import pandas as pd
from    scipy.sparse          import diags
from    scipy.sparse          import csr_matrix
from    sklearn.preprocessing import LabelEncoder
from    sltools               import pandasToSparse
from    sltools               import sparseToPandas


"""
data preparaton

"""

# fill na
def fillDscrtNAN(tableName,values):
    # values = {'genre_ids' : 'unkown' }
    tableName = tableName.fillna(value = values)
    return  tableName


def fillCntnueNAN(tableName,values):
    # a list of continue col who will be fill with mean
    # values = ['song_length']
    tableName.loc[:, values] = tableName[values].fillna(tableName[values].mean())


def scaleCntnueVariable(tableName , values):
    for value in values:
        tableName[value] = (tableName[value] - tableName[value].mean()) / tableName[value].std()




def changeNameToID(tableName,id , plan = 'A'):
    """

    :param tableName: the table name
    :param id: the primary id
    :param plan:plan A uses category.cat.codes to change the id , plan B use sklearn's encoder to encode id
    :return: return a tuple ,of which first is the table using encoded id , second is the original id
    """
    if plan == 'A':

        originalName = tableName[id]

        originalName_index = originalName.index

        originalNameUnique = originalName.unique()

        originalNameCategory = originalName.astype("category", categories=originalNameUnique).cat.codes

        mapdict = dict(zip(originalName, originalNameCategory))

        tableName[id] = originalNameCategory

        del originalName_index,originalNameUnique,originalNameCategory



        return(tableName,mapdict )

    elif plan == 'B':

        le = LabelEncoder()

        le.fit(tableName[id])

        originalName = tableName[id]

        originalNameCategory = le.transform(tableName[id])

        mapdict = dict(zip(originalName, originalNameCategory))

        tableName[id] = originalNameCategory

        return (tableName,mapdict)


def splitDF(tableName,id,colListContinue,colListDiscrete):
    colListContinue.append(id)
    colListDiscrete.append(id)
    itemCntnueAttr  = tableName[colListContinue].copy()
    itemDscrtAttr   = tableName[colListDiscrete].copy()
    return (itemCntnueAttr,itemDscrtAttr)


def tagCombine(tableName, tagColList, id, split="|"):
    #temp  =   tableName.set_index(id)
    for i in tagColList:
        tableName.loc[:,i] = tableName[i].str.strip()

    tag0 = tagColList[0]
    temp = pd.DataFrame()
    temp["concat"] = tableName[tag0].str.cat([ tableName[i] for i in tagColList if i != tag0],sep = split)
    temp = temp.set_index(tableName[id])
    return(temp)


def findNetwork(tableName,fillnawith,split = r"&|\|",plan = 'A' ):

    #tableName = songtag;split = "|" ,

    # select useful columns
    temp = tableName.copy()
    temp.reset_index(inplace =True)
    idname = tableName.index.name
    id = temp[idname]


    # split colName based on var split , due to orignal data has sth like "a|b"
    temp['splitTag'] = temp['concat'].str.split(split)

    contains = r''+'.*' + '.*'.join(fillnawith.values()) + '.*' + ''

    temp['hasNoTag'] = temp.concat.str.contains(contains)

    temp.drop( ["concat"] ,axis = 1 , inplace=True)


    temp['lenOfType'] = temp['splitTag'].map(lambda  x : len(x))

    objectHasNoTag = (id[temp.hasNoTag == True])


    colNameSpread = [ j  for i in temp['splitTag'] for j in i]
    idSpread = [ [id[i]]*j for i,j in enumerate(temp['lenOfType'])]
    idSpread = [j for i in idSpread for j in i]

    # id_colNameDF has the rows which contain the id-tag pair
    id_colNameDF = pd.DataFrame({idname:idSpread,'tag':colNameSpread})

    del temp,idSpread,colNameSpread
    gc.collect()


    # use label encoder to transform genre_id so that we can build a spasre - matrix

    # id_colNameDF[id_colNameDF[id].isin(objectHasNoTag)]

    id_colNameDF = id_colNameDF[-id_colNameDF.tag.isin([ str(i)  for  i in fillnawith.values()])]


    id_colNameDF ,colNameList = changeNameToID(id_colNameDF,'tag' ,plan= plan )


    id_colNameDF[idname] = id_colNameDF[idname].astype(int)
    id_colNameDF['tag'] = id_colNameDF['tag'].astype(int)

    #flag = id_colNameDF.ix[colNameList.astype(int) == -1,'genre_ids'].values[0]


    #id_colNameDF.ix[colNameList.astype(int) == -1,'target'] = -1
    #id_colNameDF.ix[colNameList in fillnawith.values() , 'target'] = -1

    maxcoder = max(id_colNameDF.tag.unique())
    id_colNameDF2 = pd.DataFrame({idname:objectHasNoTag,'tag':maxcoder+1})

    id_colNameDF['target'] = 1
    id_colNameDF2['target'] = -1

    id_colNameDF = pd.concat([id_colNameDF,id_colNameDF2])

    del id_colNameDF2
    gc.collect()
    ObjectTagmatrix = csr_matrix((id_colNameDF['target'], (id_colNameDF[idname], id_colNameDF['tag'])))
    del id_colNameDF
    gc.collect()

    return(ObjectTagmatrix,objectHasNoTag.values)


def LargeSparseMatrixCosine(largeSparseMatrix,ObjectNoAttr,
                            num = 5000,select = 0.7,
                            fileplace = "D:\\tempdata\\",
                            prefix = "item"
                            ):

    # this method will save the result in disk
    (rowNum,colNum) = largeSparseMatrix.shape
    sep = np.linspace(0,rowNum,endpoint=True,dtype=np.int64,num=num)
    # calculate the L2 of each vector
    lenOfVec = np.sqrt(largeSparseMatrix.multiply(largeSparseMatrix).\
                            sum(axis=1).A.ravel()
                            )
    lenOfVecAll = diags(1 / lenOfVec)
    print("#############  please  be patient ############## \n \n")
    for index,value in enumerate(sep):
        if index+1 < len(sep):
        #if i < 40:
            #print(i,j)
            # get a block from the ogininal matrix
            block_of_sparse = largeSparseMatrix[value:sep[index+1],:]

            # calculate the dot
            dot_product_of_block = block_of_sparse.dot(
                                        largeSparseMatrix.transpose()
                                    )
            lenOfBlockVec = diags(1/ lenOfVec[value:sep[index+1]])

            dot_cosine = lenOfBlockVec @ dot_product_of_block @ lenOfVecAll

            #　we just select few of them to build net work

            ######  the following lines is to deal with Object with no tags  #####


            dot_cosine[dot_cosine<0] = 1

            dot_cosine[:,ObjectNoAttr] = 0

            dot_cosine[ObjectNoAttr,ObjectNoAttr] = 1
            ######################################################################


            dot_cosine = dot_cosine > select

            gc.collect()


            if index == 0:
                # if its the first loop
                # check if dot_cosine.h5 is exists or not
                # if exists , clean it
                # create the file dot_cosine.h5
                with  h5py.File(fileplace+prefix+"dot_cosine.h5") as h5f:
                    for key in h5f.keys():
                        del h5f[key]
                with h5sparse.File(fileplace+prefix+"dot_cosine.h5") as h5f:
                    h5f.create_dataset(
                        "dot_cosineData/data", data=dot_cosine,
                        chunks=(10000,), maxshape=(None,)
                    )
            else:
                with h5sparse.File(fileplace+prefix+"dot_cosine.h5") as h5f:
                    h5f['dot_cosineData/data'].append(dot_cosine)


            del dot_cosine,lenOfBlockVec,h5f
            gc.collect()
            print("Social net work for " + prefix +  " is now  preparing ")
            preparePercent = (1+index)/(len(sep)-1)
            preparePercent = round(preparePercent,4)
            print(str(preparePercent) ," percent of Social Network is prepared ")
    print("#####  social net work data for  " +prefix +"  is prepared successful   ##########")



def largeMatrixDis(largeDisMatrix,num = 2,
                   netFilePlace =  "C:\\Users\\22560\\Desktop\\",
                   prefix = "item"):
    # load the social network
    with  h5sparse.File(netFilePlace + prefix+"dot_cosine.h5") as h5f:

        (rowNum, colNum) =largeDisMatrix.shape
        sep = np.linspace(0, rowNum, endpoint=True, dtype=np.int64, num=num)
        yTy = (largeDisMatrix*largeDisMatrix).sum(1)
        print("#############  please  be patient ############## \n \n")
        for i,j in enumerate(sep):
            if i + 1 < len(sep):
                blockSlice = slice(j,sep[i+1])
                blockData = largeDisMatrix[blockSlice,:]
                negtive2xTy = -2*blockData.dot(largeDisMatrix.transpose())
                xTx   = yTy[blockSlice]
                xTx   = xTx.reshape((len(xTx),1))


                dis = yTy+ negtive2xTy + xTx
                dis = csr_matrix(dis)

                sparse = h5f['dot_cosineData/data'][blockSlice]


                dis = dis.multiply(sparse)

                if i == 0:
                    # if its the first loop
                    # check if dot_cosine.h5 is exists or not
                    # if exists , clean it
                    # create the file dot_cosine.h5
                    with  h5py.File(netFilePlace+prefix+"dis.h5") as h5file:
                        for key in h5file.keys():
                            del h5file[key]
                    with h5sparse.File(netFilePlace+prefix+"dis.h5") as h5file:
                        h5file.create_dataset(
                            "disData/data", data=dis,
                            chunks=(10000,), maxshape=(None,)
                        )
                else:
                    with h5sparse.File(netFilePlace+prefix+"dis.h5") as h5file:
                        h5file['disData/data'].append(dis)

                print("Dis for "+prefix+" is now  preparing ")
                preparePercent = (1 + i) / (len(sep) - 1)
                preparePercent = round(preparePercent, 4)
                print(str(preparePercent), " percent of Distance data is prepared ")
        print("############# dis data for "+ prefix +" prepared successful!! ###########")


def subtractIdx(ObservationData, totalLen, encoded=True):
    """

    :param ObservationData: the data of (usr, item , value)
    :param totalLen is the number of observation
    :param encoded : using for determine  the usr , item had coded or not
    :return: usr list , item list , rlist , using in the process of calling distance
    """
    if encoded == True:
        # return a test tuple for next method
        ulist = np.arange(totalLen)
        ilist = np.arange(totalLen)
        rlist = np.arange(totalLen)
        return (ulist, ilist, rlist)

    else:
        pass


def kernelOperator(disSquare, bandwith=4, ker="gauss"):
    """

    :param disSquare:  return the distance of Xui & X_omiga
    :param bandwith : the bandwith of kernel
    :param kernel :which kernel you may use
    :return:
    """
    if ker == "gauss":
        x = np.sqrt(disSquare) / bandwith
        core = np.exp(abs(x))
        return core


def yGenerator(ObjectNum, mode="usr", parallel=True):
    global usrDis, itemDis, usrNet, itemNet, ulist, ilist, rlist

    if parallel == True:
        pass
    else:
        if mode == "usr":
            uid = ObjectNum
            """
                 S_u_omiga : is the s for usr to omiga
                 S_i_omiga : is the s for item to omiga
                 d_u_omiga : is the dis of usr to omiga
                 d_i_omiga : is the dis of item to omiga

            """

            itemNum = itemDis.shape[0]
            S_u_omiga = np.array([usrNet[ObjectNum, ulist] for _ in range(itemNum)])
            S_i_omiga = itemNet[:, ilist]
            SocialNetWork = S_i_omiga * S_u_omiga

            d_u_omiga = np.array([usrDis[ObjectNum, ulist] for _ in range(itemNum)])
            d_i_omiga = itemDis[:, ilist]

            disSquare = d_i_omiga * d_u_omiga

            kernel = kernelOperator(disSquare)

            y = kernel * SocialNetWork.dot(rlist)
            return (y)

        elif mode == "item":
            pass












